// Only PEReader/MetadataReader are used. Target assemblies are never loaded.
using System;
using System.IO;
using System.Linq;
using System.Collections.Generic;
using System.Reflection;
using System.Reflection.Emit;
using System.Reflection.Metadata;
using System.Reflection.Metadata.Ecma335;
using System.Reflection.PortableExecutable;
using System.Text.RegularExpressions;

public static class TD2ManagedInspector
{
    static Dictionary<ushort, OpCode> Codes = typeof(OpCodes).GetFields(BindingFlags.Public | BindingFlags.Static)
        .Where(f => f.FieldType == typeof(OpCode)).Select(f => (OpCode)f.GetValue(null))
        .ToDictionary(o => unchecked((ushort)o.Value));

    static string Entity(MetadataReader md, EntityHandle handle)
    {
        switch (handle.Kind)
        {
            case HandleKind.MethodDefinition:
                var m = md.GetMethodDefinition((MethodDefinitionHandle)handle);
                return Entity(md, m.GetDeclaringType()) + "::" + md.GetString(m.Name);
            case HandleKind.MemberReference:
                var member = md.GetMemberReference((MemberReferenceHandle)handle);
                return Entity(md, member.Parent) + "::" + md.GetString(member.Name);
            case HandleKind.FieldDefinition:
                var f = md.GetFieldDefinition((FieldDefinitionHandle)handle);
                return Entity(md, f.GetDeclaringType()) + "::" + md.GetString(f.Name);
            case HandleKind.TypeDefinition:
                var t = md.GetTypeDefinition((TypeDefinitionHandle)handle);
                return md.GetString(t.Namespace) + "." + md.GetString(t.Name);
            case HandleKind.TypeReference:
                var tr = md.GetTypeReference((TypeReferenceHandle)handle);
                return md.GetString(tr.Namespace) + "." + md.GetString(tr.Name);
            case HandleKind.MethodSpecification: return Entity(md, md.GetMethodSpecification((MethodSpecificationHandle)handle).Method);
            default: return handle.Kind.ToString();
        }
    }

    static List<object> IL(PEReader pe, MetadataReader md, MethodDefinition method)
    {
        var result = new List<object>();
        if (method.RelativeVirtualAddress == 0) return result;
        byte[] bytes = pe.GetMethodBody(method.RelativeVirtualAddress).GetILBytes();
        for (int p = 0; p < bytes.Length;)
        {
            int start = p;
            ushort code = bytes[p++];
            if (code == 0xfe) code = (ushort)(0xfe00 | bytes[p++]);
            if (!Codes.TryGetValue(code, out OpCode op)) throw new InvalidDataException("Unknown IL opcode");
            int size = 0; object operand = null;
            switch (op.OperandType)
            {
                case OperandType.InlineNone: break;
                case OperandType.ShortInlineI: size = 1; operand = (sbyte)bytes[p]; break;
                case OperandType.ShortInlineVar: size = 1; operand = bytes[p]; break;
                case OperandType.InlineVar: size = 2; operand = BitConverter.ToUInt16(bytes, p); break;
                case OperandType.InlineI: size = 4; operand = BitConverter.ToInt32(bytes, p); break;
                case OperandType.InlineI8: size = 8; operand = BitConverter.ToInt64(bytes, p); break;
                case OperandType.ShortInlineR: size = 4; operand = BitConverter.ToSingle(bytes, p); break;
                case OperandType.InlineR: size = 8; operand = BitConverter.ToDouble(bytes, p); break;
                case OperandType.ShortInlineBrTarget: size = 1; operand = p + 1 + (sbyte)bytes[p]; break;
                case OperandType.InlineBrTarget: size = 4; operand = p + 4 + BitConverter.ToInt32(bytes, p); break;
                case OperandType.InlineSwitch: size = 4 + 4 * BitConverter.ToInt32(bytes, p); break;
                case OperandType.InlineString:
                    size = 4;
                    string value = md.GetUserString(MetadataTokens.UserStringHandle(BitConverter.ToInt32(bytes, p) & 0xffffff));
                    // Reject unrelated service/config data, including opaque tokens.
                    bool sensitive = Regex.IsMatch(value, @"https?://|password|secret|token|api.?key|private.?key|credential|BEGIN .*KEY|^[A-Za-z0-9_\-+/=]{40,}$", RegexOptions.IgnoreCase);
                    operand = sensitive ? "发现与任务无关的敏感配置，已跳过。" : value;
                    break;
                default:
                    size = 4;
                    int token = BitConverter.ToInt32(bytes, p);
                    var entity = MetadataTokens.EntityHandle(token);
                    string signature = "";
                    if (entity.Kind == HandleKind.MemberReference) signature = BitConverter.ToString(md.GetBlobBytes(md.GetMemberReference((MemberReferenceHandle)entity).Signature)).Replace("-", "");
                    if (entity.Kind == HandleKind.MethodDefinition) signature = BitConverter.ToString(md.GetBlobBytes(md.GetMethodDefinition((MethodDefinitionHandle)entity).Signature)).Replace("-", "");
                    operand = new Dictionary<string, object> {{"token", "0x" + token.ToString("x8")}, {"name", Entity(md, entity)}, {"signature", signature}};
                    break;
            }
            if (p + size > bytes.Length) throw new InvalidDataException("Truncated IL operand");
            result.Add(new Dictionary<string, object> {{"offset", start}, {"opcode", op.Name}, {"operand", operand}});
            p += size;
        }
        return result;
    }

    public static Dictionary<string, object> Inspect(string path, long offset, int length, string selector)
    {
        byte[] bytes = new byte[length];
        using (var input = File.OpenRead(path)) {
            input.Position = offset;
            int read = 0;
            while (read < length) { int n = input.Read(bytes, read, length - read); if (n == 0) throw new EndOfStreamException(); read += n; }
        }
        return InspectData(bytes, selector);
    }

    public static Dictionary<string, object> InspectData(byte[] bytes, string selector)
    {
        using (var pe = new PEReader(new MemoryStream(bytes, false))) {
            var md = pe.GetMetadataReader();
            var assembly = md.GetAssemblyDefinition();
            var resources = new List<object>();
            foreach (var handle in md.ManifestResources) {
                var resource = md.GetManifestResource(handle);
                resources.Add(new Dictionary<string, object> {{"name", md.GetString(resource.Name)}, {"offset", resource.Offset}, {"embedded", resource.Implementation.IsNil}});
            }
            var types = new List<object>();
            foreach (var handle in md.TypeDefinitions) {
                var type = md.GetTypeDefinition(handle);
                string name = md.GetString(type.Namespace) + "." + md.GetString(type.Name);
                bool selected = selector.Length != 0 && Regex.IsMatch(name, selector);
                var methods = new List<object>();
                foreach (var mh in type.GetMethods()) {
                    var method = md.GetMethodDefinition(mh);
                    methods.Add(new Dictionary<string, object> {{"name", md.GetString(method.Name)}, {"token", "0x" + MetadataTokens.GetToken(mh).ToString("x8")}, {"rva", method.RelativeVirtualAddress}, {"il", selected ? IL(pe, md, method) : null}});
                }
                types.Add(new Dictionary<string, object> {{"name", name}, {"fields", type.GetFields().Select(f => md.GetString(md.GetFieldDefinition(f).Name)).ToArray()}, {"methods", methods}});
            }
            return new Dictionary<string, object> {
                {"name", md.GetString(assembly.Name)}, {"assembly_version", assembly.Version.ToString()},
                {"metadata_version", md.MetadataVersion}, {"machine", pe.PEHeaders.CoffHeader.Machine.ToString()},
                {"resources_directory_rva", pe.PEHeaders.CorHeader.ResourcesDirectory.RelativeVirtualAddress},
                {"references", md.AssemblyReferences.Select(h => md.GetString(md.GetAssemblyReference(h).Name)).ToArray()},
                {"resources", resources}, {"types", types}
            };
        }
    }
}
