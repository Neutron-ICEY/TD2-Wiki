import json
import tempfile
import unittest
from pathlib import Path

from tools.publish.bundle import build, digest, report_for, title_key, verify_bundle
from tools.publish.publisher import ManualPublisher


class PublishingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.registry_path = self.root / "registry.json"
        self.baseline_path = self.root / "baseline.json"
        self.snapshot_path = self.root / "snapshot.json"
        self.output = self.root / "dist" / "review"
        self.registry = {
            "schema_version": 1, "mode": "MANUAL", "target": "test-wiki",
            "namespace_prefixes": {"0": [""], "6": ["File"], "10": ["Template"],
                                   "14": ["Category"], "828": ["Module"]}, "entries": []}
        self.baseline = {"schema_version": 1, "target": "test-wiki", "entries": []}

    def write_json(self, path, value):
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")

    def add(self, entry_id="item", kind="pages", title="Item", namespace=0,
            text="Example data\n", ownership="generated", suffix=".wiki"):
        relative = f"assets/{entry_id}{suffix}" if kind == "assets" else f"wiki/{kind}/{entry_id}{suffix}"
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text if isinstance(text, bytes) else text.encode("utf-8"))
        row = {"id": entry_id, "kind": kind, "source": relative, "title": title,
               "namespace": namespace, "related_entity": "item:example", "ownership": ownership,
               "generator": "fixture@v1", "change_reason": "Fixture change", "asset_relationships": []}
        if kind == "assets":
            row["content_sha256"] = digest(path.read_bytes())
        self.registry["entries"].append(row)
        return row

    def state(self, row, content=None):
        data = (self.root / row["source"]).read_bytes() if content is None else content
        state = {"title": row["title"], "namespace": row["namespace"], "content_hash": digest(data),
                 "revision_id": 101, "reviewed_by": "reviewer", "published_at": "2026-10-03T12:00:00Z"}
        if row["namespace"] == 6:
            state["file_revision"] = "upload-version-1"
        return state

    def test_registered_asset_digest_is_required_and_must_match_exported_bytes(self):
        image = self.add('image', 'assets', 'File:Image.png', 6, b'original', suffix='.png')
        bad_values = [(None, 'ASSET_SHA256_REQUIRED'), ('bad', 'ASSET_SHA256_REQUIRED'),
                      (digest(b'old bytes'), 'ASSET_BYTES_CHANGED')]
        for value, diagnostic in bad_values:
            with self.subTest(value=value):
                if value is None:
                    image.pop('content_sha256')
                else:
                    image['content_sha256'] = value
                with self.assertRaisesRegex(ValueError, diagnostic + ': image'):
                    self.run_build()
                self.assertFalse(self.output.exists())

    def test_huiji_asset_rejects_svg_source_or_file_title_before_build(self):
        self.registry["target"] = self.baseline["target"] = "huijiwiki-td2"
        for suffix, title in [(".svg", "File:Art.png"), (".png", "File:Art.SVG")]:
            with self.subTest(suffix=suffix, title=title):
                self.output = self.root / "dist" / suffix[1:]
                self.registry["entries"].clear()
                self.add("art", "assets", title, 6, b"fixture", suffix=suffix)
                with self.assertRaisesRegex(ValueError, "SVG"):
                    self.run_build()
                self.assertFalse(self.output.exists())

    def test_svg_bundle_for_another_target_cannot_be_prepared_for_huiji(self):
        self.add("art", "assets", "File:Art.svg", 6, b"<svg/>", suffix=".svg")
        manifest = self.run_build()
        self.assertIn("File:Art.svg", ManualPublisher().prepare(self.output))
        manifest["target"] = "huijiwiki-td2"
        for suffix in (".svg", ".png"):
            with self.subTest(declared_suffix=suffix):
                # The existing bundle payload is still art.svg.
                manifest["entries"][0].update(source="assets/art" + suffix, title="File:Art" + suffix)
                self.reseal_for_test(manifest)
                with self.assertRaisesRegex(ValueError, "SVG"):
                    ManualPublisher().prepare(self.output)

    def test_equipment_lua_image_fields_resolve_registered_weapons_and_skins(self):
        images = [self.add(key, 'assets', 'File:'+filename, 6, key.encode(), suffix='.png')
                  for key, filename in [('weapon', 'TD2-Weapon-Test.png'), ('skin', 'TD2-Weapon-Skin-Test.png')]]
        self.add('equipment-mapping-data', 'modules', 'Module:TD2装备映射', 828,
                 'return {["image"]="TD2-Weapon-Test.png", ["skins"]={{["image"]="TD2-Weapon-Skin-Test.png"}},'
                 '["description"]="TD2-Other.png"}', suffix='.lua')
        entries = self.run_build()['entries']
        data = next(i for i in entries if i['id']=='equipment-mapping-data')
        self.assertEqual(set(data['asset_relationships']), {i['id'] for i in images})
        self.assertTrue(all(entries.index(i)<entries.index(data) for i in entries if i['kind']=='assets'))

    def test_equipment_lua_unregistered_skin_blocks_build(self):
        self.add('equipment-mapping-data', 'modules', 'Module:TD2装备映射', 828,
                 'return {["skins"]={{["image"]="TD2-Unknown-Skin.png"}}}', suffix='.lua')
        with self.assertRaisesRegex(ValueError, '未登记的装备图片: TD2-Unknown-Skin.png'):
            self.run_build()
        self.assertFalse(self.output.exists())

    def test_new_shared_asset_precedes_every_consumer_without_a_manual_edge(self):
        provider = self.add('icons', 'templates', 'Template:Icons', 10, '{{#switch:{{{1}}}|icon=TD2-Test.png}}')
        nav = self.add('nav', 'templates', 'Template:Nav', 10,
                       '[[文件:TD2-test.png|a]] [[:Image:TD2-Test.png|b]] {{TD2资产|new-art}} '
                       '<!--[[File:Comment.png]]--><nowiki>[[File:Example.png]]</nowiki>')
        logo = self.add('logo', 'templates', 'Template:Logo', 10, '[[File:{{{filename}}}]]')
        logo['asset_relationship_source'] = provider['id']
        helper = self.add('addresses', 'templates', 'Template:Addresses', 10)
        helper['asset_relationship_source'] = 'registry-assets'
        ordinary_page = self.add('article', title='Article')
        image = self.add('new-art', 'assets', 'File:TD2-Test.png', 6, b'new art', suffix='.png')
        entries = self.run_build()['entries']
        order = [row['id'] for row in entries]
        for source in (provider, nav, logo, helper):
            position = order.index(source['id'])
            self.assertEqual(entries[position]['asset_relationships'], [image['id']])
            self.assertLess(order.index(image['id']), position)
            self.assertLess(position, order.index(ordinary_page['id']))
            self.assertEqual(source['asset_relationships'], [])
        report = ManualPublisher().prepare(self.output).split('## CREATE')[0]
        self.assertLess(report.index(image['title']), report.index(nav['title']))

    def test_new_and_removed_file_links_follow_the_next_candidate(self):
        page = self.add(text='[[File:Old.png]]')
        self.add('old', 'assets', 'File:Old.png', 6, b'old', suffix='.png')
        first = {row['id']: row for row in self.run_build()['entries']}
        self.assertEqual(first[page['id']]['asset_relationships'], ['old'])
        self.add('new', 'assets', 'File:New.png', 6, b'new', suffix='.png')
        (self.root / page['source']).write_bytes(b'[[File:New.png]]')
        self.output = self.root / 'dist/next'
        second = {row['id']: row for row in self.run_build()['entries']}
        self.assertEqual(second[page['id']]['asset_relationships'], ['new'])

    def test_unknown_literals_stable_ids_and_lookup_sources_are_diagnosed(self):
        row = self.add('shared', 'templates', 'Template:Cards', 10)
        for source in ['[[File:TD2-Missing.png|thumb]]', '{{TD2资产|missing}}', '{{TD2资产|bad id}}',
                       '<nowiki/>[[File:Missing.png]]<nowiki>[[File:Displayed.png]]</nowiki>',
                       '{{#switch:{{{1}}}|missing=TD2-Missing.png}}']:
            with self.subTest(source=source):
                (self.root / row['source']).write_bytes(source.encode())
                with self.assertRaisesRegex(ValueError, '未登记'):
                    self.run_build()
        (self.root / row['source']).write_bytes(b'{{{file}}}')
        row['asset_relationship_source'] = 'unregistered-provider'
        with self.assertRaisesRegex(ValueError, '提供模板'):
            self.run_build()

    def test_asset_cycles_are_rejected_before_creating_output(self):
        first = self.add('a', 'assets', 'File:A.png', 6, b'A', suffix='.png')
        second = self.add('b', 'assets', 'File:B.png', 6, b'B', suffix='.png')
        first['asset_relationships'] = ['b']
        second['asset_relationships'] = ['a']
        with self.assertRaisesRegex(ValueError, '循环'):
            self.run_build()
        self.assertFalse(self.output.exists())

    def test_prepare_checks_actual_references_and_order_after_resealing(self):
        self.add('consumer', text='[[File:TD2-image-Icon.png]]')
        self.add('unused', 'assets', 'File:Unused.png', 6, b'unused', suffix='.png')
        old_address, new_address = self.add_move('image', 6)
        original = self.run_build([old_address, new_address])
        by_id = {r['id']: r for r in original['entries']}
        image, consumer = by_id['image'], by_id['consumer']
        self.assertTrue(image['pending_move_from'])
        self.assertEqual(consumer['asset_relationships'], ['image'])
        report = ManualPublisher().prepare(self.output).split('## CREATE')[0]
        self.assertLess(report.index(image['title']), report.index(consumer['title']))
        for change, diagnostic in [('omit', '依赖与来源不符'), ('extra', '依赖与来源不符'), ('reverse', '依赖顺序')]:
            with self.subTest(change=change):
                manifest = json.loads(json.dumps(original))
                row = next(r for r in manifest['entries'] if r['id'] == 'consumer')
                if change == 'omit':
                    row['asset_relationships'] = []
                elif change == 'extra':
                    row['asset_relationships'].append('unused')
                else:
                    manifest['entries'].reverse()
                self.reseal_for_test(manifest)
                with self.assertRaisesRegex(ValueError, diagnostic):
                    ManualPublisher().prepare(self.output)

    def reseal_for_test(self, manifest):
        self.write_json(self.output / 'manifest.json', manifest)
        (self.output / 'publish-report.md').write_bytes(report_for(manifest).encode())
        validation = json.loads((self.output / 'validation.json').read_bytes())
        validation['manifest_hash'] = digest((self.output / 'manifest.json').read_bytes())
        validation['report_hash'] = digest((self.output / 'publish-report.md').read_bytes())
        self.write_json(self.output / 'validation.json', validation)

    def run_build(self, snapshot=None):
        self.write_json(self.registry_path, self.registry)
        self.write_json(self.baseline_path, self.baseline)
        if snapshot is not None:
            self.write_json(self.snapshot_path, {"schema_version": 1, "target": "test-wiki", "entries": snapshot})
        return build(self.root, self.registry_path, self.baseline_path, self.output,
                     self.snapshot_path if snapshot is not None else None)

    def test_address_moves_keep_old_baseline_and_never_imply_publication(self):
        row=self.add(title='类型-Item')
        old=dict(self.state(row),title='Item');self.baseline['entries']=[old]
        location=self.root/'publishing/pending-moves.json';location.parent.mkdir()
        self.write_json(location,{'schema_version':1,'status':'LOCAL_ONLY_NOT_PUBLISHED','entries':[{'id':row['id'],'namespace':0,'from_title':'Item','from_source':'wiki/pages/old.wiki'}]})
        manifest=self.run_build()
        self.assertEqual(manifest['delete_candidates'],[])
        self.assertEqual(manifest['address_moves'][0]['baseline_revision'],101)
        self.assertEqual(manifest['address_moves'][0]['status'],'NOT_EXECUTED')
        self.assertIsNone(manifest['address_moves'][0]['target_observation'])
        self.assertIn('ADDRESS_MIGRATION_REQUIRES_REVIEW',manifest['entries'][0]['conflicts'])
        self.assertEqual(json.loads(self.baseline_path.read_text('utf8'))['entries'],[old])
        self.assertIn('`Item` → `类型-Item`',ManualPublisher().prepare(self.output))

    def add_move(self, entry_id, namespace):
        asset = namespace == 6
        row = self.add(entry_id, 'assets' if asset else 'pages',
                       f'File:TD2-{entry_id}-Icon.png' if asset else f'类型-{entry_id}',
                       namespace, suffix='.png' if asset else '.wiki')
        old = dict(self.state(row), title=f'File:旧-{entry_id}.png' if asset else entry_id,
                   exists=True, observed_at='2026-11-16T09:00:00Z')
        target = dict(title=row['title'], namespace=namespace, exists=False, observed_at=old['observed_at'])
        location = self.root / 'publishing/pending-moves.json'
        location.parent.mkdir(exist_ok=True)
        transaction = json.loads(location.read_text('utf8')) if location.exists() else {
            'schema_version': 1, 'status': 'LOCAL_ONLY_NOT_PUBLISHED', 'entries': []}
        transaction['entries'].append(dict(id=entry_id, namespace=namespace, from_title=old['title'], from_source=row['source']))
        self.write_json(location, transaction)
        return old, target

    def test_native_moves_separate_file_redirects_and_page_redirects(self):
        page = self.add_move('page', 0)
        image = self.add_move('image', 6)
        manifest = self.run_build([*page, *image])
        moves = {r['id']: r for r in manifest['address_moves']}
        self.assertEqual(moves['page']['execution_action'], 'MOVE_PAGE_KEEP_REDIRECT')
        self.assertIs(moves['page']['move_options']['noredirect'], False)
        self.assertEqual(moves['image']['execution_action'], 'MOVE_FILE_NO_REDIRECT_KEEP_HISTORY')
        self.assertIs(moves['image']['move_options']['noredirect'], True)
        self.assertTrue(all(r['move_options']['preserve_history'] and r['move_options']['reason'] == '' for r in moves.values()))
        self.assertEqual(manifest['file_write_policy']['summary'], '')
        self.assertEqual(manifest['file_write_policy']['new_description'], '')
        report = ManualPublisher().prepare(self.output)
        self.assertNotIn('TD2-image', report.split('## UPLOAD\n', 1)[1].split('## UNCHANGED', 1)[0])
        self.assertNotIn('类型-page', report.split('## CREATE\n', 1)[1].split('## UPDATE', 1)[0])

    def test_missing_unobserved_and_occupied_move_sources_never_imply_copy_upload(self):
        snapshot = []
        for entry_id, namespace in [('absent-image', 6), ('absent-page', 0), ('occupied', 6), ('unknown', 6)]:
            old, target = self.add_move(entry_id, namespace)
            if entry_id.startswith('absent'):
                old['exists'] = False
            if entry_id == 'occupied':
                target = dict(old, title=target['title'])
            if entry_id != 'unknown':
                snapshot.extend([old, target])
        moves = {r['id']: r['execution_action'] for r in self.run_build(snapshot)['address_moves']}
        self.assertEqual(moves, {'absent-image': 'FIRST_UPLOAD_REQUIRES_APPROVAL',
                                'absent-page': 'CREATE_PAGE_REQUIRES_APPROVAL',
                                'occupied': 'HOLD_TARGET_OCCUPIED', 'unknown': 'HOLD_ADDRESS_PREFLIGHT'})

    def test_pending_move_cannot_override_redirect_policy(self):
        self.add_move('image', 6)
        path = self.root / 'publishing/pending-moves.json'
        data = json.loads(path.read_text('utf8'))
        data['entries'][0]['noredirect'] = False
        self.write_json(path, data)
        with self.assertRaisesRegex(ValueError, 'override'):
            self.run_build()
        self.assertFalse(self.output.exists())

    def test_known_move_source_must_match_its_observed_version(self):
        snapshots = []
        cases = [('matched', {}), ('revision', {'revision_id': 102}), ('hash', {'content_hash': digest(b'changed')}),
                 ('file-version', {'file_revision': 'other-upload'}), ('removed', {'exists': False})]
        for entry_id, change in cases:
            old, target = self.add_move(entry_id, 6)
            self.baseline['entries'].append(old)
            snapshots.extend([{**old, **change}, target])
        manifest = self.run_build(snapshots)
        moves = {m['id']: m for m in manifest['address_moves']}
        self.assertEqual(moves['matched']['execution_action'], 'MOVE_FILE_NO_REDIRECT_KEEP_HISTORY')
        entries = {r['id']: r for r in manifest['entries']}
        for entry_id, _ in cases[1:]:
            with self.subTest(entry=entry_id):
                self.assertEqual(moves[entry_id]['execution_action'], 'HOLD_SOURCE_DRIFT')
                self.assertIn('MOVE_SOURCE_DRIFT', entries[entry_id]['conflicts'])
        self.assertIn('HOLD_SOURCE_DRIFT', ManualPublisher().prepare(self.output))
        moves['revision']['execution_action'] = moves['matched']['execution_action']
        self.reseal_for_test(manifest)
        with self.assertRaisesRegex(ValueError, 'Move action'):
            ManualPublisher().prepare(self.output)

    def test_offline_validation_requires_explicit_false_approval(self):
        self.add()
        self.run_build()
        path = self.output / 'validation.json'
        original = json.loads(path.read_text('utf8'))
        for approval in ({}, {'production_approved': True}, {'production_approved': 0}, {'production_approved': 'false'}):
            with self.subTest(approval=approval):
                self.write_json(path, {**{k: v for k,v in original.items() if k != 'production_approved'}, **approval})
                with self.assertRaisesRegex(ValueError, 'production_approved'):
                    ManualPublisher().prepare(self.output)

    def test_prepare_rejects_unsafe_move_contract_even_with_resealed_hashes(self):
        original = self.run_build(list(self.add_move('image', 6)))
        mutations = [lambda m: m['address_moves'][0]['move_options'].update(noredirect=False),
                     lambda m: m['address_moves'][0].pop('move_options'),
                     lambda m: m['address_moves'][0]['move_options'].update(reason='extra text'),
                     lambda m: m['address_moves'][0].update(execution_action='MOVE_FILE_KEEP_REDIRECT_AND_HISTORY'),
                     lambda m: m['address_moves'][0].update(status='PUBLISHED_VERIFIED'),
                     lambda m: m['file_write_policy'].update(summary='extra text'),
                     lambda m: m['file_write_policy'].update(new_description='extra text')]
        for index, mutate in enumerate(mutations):
            with self.subTest(case=index):
                manifest = json.loads(json.dumps(original))
                mutate(manifest)
                self.write_json(self.output / 'manifest.json', manifest)
                # Resealing metadata must not bypass semantic prepare validation.
                validation = json.loads((self.output / 'validation.json').read_text('utf8'))
                validation['manifest_hash'] = digest((self.output / 'manifest.json').read_bytes())
                self.write_json(self.output / 'validation.json', validation)
                with self.assertRaises(ValueError):
                    ManualPublisher().prepare(self.output)

    def test_retained_retired_baseline_does_not_become_deletion_candidate(self):
        self.add()
        retired = dict(self.state(self.registry['entries'][0]), title='Form:品牌套装新版', namespace=106, retired=True)
        self.baseline['entries'] = [retired]
        self.assertEqual(self.run_build()['delete_candidates'], [])
        self.assertEqual(self.baseline['entries'][0], retired)

    def test_registered_weapon_titles_preserve_equipment_redirects(self):
        root = Path(__file__).resolve().parents[1]
        registry = json.loads((root / 'publishing/registry.json').read_text('utf8'))['entries']
        baseline = json.loads((root / 'publishing/baseline.json').read_text('utf8'))['entries']
        reserved = {title_key(r['title'], 0) for r in baseline
                    if r['namespace'] == 0 and r.get('operation') == 'RETAINED_REDIRECT'}
        pages = {r['related_entity']: r for r in registry if r['kind'] == 'pages'}
        weapons = {title_key(r['title'], 0) for r in pages.values()
                   if (r['related_entity'] or '').startswith('weapon:')}
        self.assertFalse(weapons & reserved)
        self.assertIn(title_key('煽动者', 0), reserved)
        self.assertEqual(pages['exotic:b0050135668e79e60005319dc2f2754c']['title'], '奇特装备-煽动者')
        weapon = pages['weapon:b005013569a6abf100317bb7f32d5a19']
        self.assertEqual(weapon['title'], '奇特武器-煽动者')
        sources = {r['id']: (root / r['source']) for r in registry}
        self.assertIn('[[奇特武器-煽动者|煽动者]]', sources['mechanic-threat'].read_text('utf8'))
        self.assertIn('data-target="奇特武器-煽动者"', sources['weapon-navigation'].read_text('utf8'))

    def test_formal_resource_titles_are_retained_without_expanding_exports(self):
        row = self.add()
        config = self.root / 'publishing/reader-editor-production.json'
        config.parent.mkdir()
        self.write_json(config, {'resource_naming': {
            'reader': [{'title': 'Gadget:Reader.css'}, {'title': 'Gadget:Reader.js'}],
            'runtime_title': 'Gadget:Runtime.js', 'entry_title': 'Gadget:Entry.js',
            'gadgets': [{'name': name} for name in ('Style', 'Scripts', 'Editor')],
        }})
        retained = [('零件:' + name, 2300) for name in ('Reader.css', 'Reader.js', 'Runtime.js', 'Entry.js')]
        retained += [('零件定义:' + name, 2302) for name in ('Style', 'Scripts', 'Editor')]
        retained += [('MediaWiki:Gadget-' + name, 8) for name in ('Style', 'Scripts', 'Editor')]
        removed = [('零件:Old.js', 2300), ('零件定义:Old', 2302), ('MediaWiki:Gadget-Old', 8), ('Removed', 0)]
        self.baseline['entries'] = [dict(self.state(row), title=title, namespace=namespace)
                                    for title, namespace in retained + removed]
        original = json.dumps(self.baseline, ensure_ascii=False)
        result = self.run_build()
        self.assertEqual([(entry['id'], entry['operation']) for entry in result['entries']], [('item', 'create')])
        self.assertEqual({(entry['title'], entry['namespace']) for entry in result['delete_candidates']}, set(removed))
        self.assertEqual(json.dumps(json.loads(self.baseline_path.read_text(encoding='utf8')), ensure_ascii=False), original)
        self.assertIn('零件:Old.js', ManualPublisher().prepare(self.output))

    def test_removed_formal_mapping_remains_a_deletion_candidate(self):
        row = self.add()
        config = self.root / 'publishing/reader-editor-production.json'
        config.parent.mkdir()
        self.write_json(config, {'resource_naming': {
            'reader': [{'title': 'Gadget:NewReader.js'}],
            'runtime_title': 'Gadget:Runtime.js', 'entry_title': 'Gadget:Entry.js',
            'gadgets': [],
        }})
        self.baseline['entries'] = [dict(self.state(row), title='零件:Reader.js', namespace=2300)]
        self.assertEqual([entry['title'] for entry in self.run_build()['delete_candidates']], ['零件:Reader.js'])

    def test_six_kinds_and_manual_source_preserved(self):
        manual = self.add(ownership="manual", text="Human narrative\n")
        self.add("template", "templates", "Template:Item", 10)
        self.add("module", "modules", "Module:Item", 828, "return {}\n", suffix=".lua")
        self.add("category", "categories", "Category:Items", 14)
        self.add("redirect", "redirects", "Alias", 0, "#REDIRECT [[Item]]\n")
        self.add("image", "assets", "File:Item.png", 6, b"fixture asset bytes", suffix=".png")
        manual["asset_relationships"] = ["image"]
        original = (self.root / manual["source"]).read_bytes()
        manifest = self.run_build()
        self.assertEqual(len(manifest["entries"]), 6)
        self.assertEqual((self.root / manual["source"]).read_bytes(), original)
        self.assertTrue(all(r["conflicts"] == ["REMOTE_UNVERIFIED"] for r in manifest["entries"]))
        report = ManualPublisher().prepare(self.output)
        for heading in ("CREATE", "UPDATE", "UPLOAD", "UNCHANGED", "CONFLICT", "DELETE"):
            self.assertIn(f"## {heading}", report)
        self.assertIn("File:Item.png", report)
        self.assertEqual(verify_bundle(self.output), manifest)

    def test_local_operations_and_deletion_candidates(self):
        self.add("new", title="New")
        changed = self.add("changed", title="Changed")
        same = self.add("same", title="Same")
        self.baseline["entries"] = [self.state(changed, b"Old\n"), self.state(same),
                                    dict(self.state(same), title="Removed")]
        result = self.run_build()
        self.assertEqual({r["id"]: r["operation"] for r in result["entries"]},
                         {"new": "create", "changed": "update", "same": "unchanged"})
        self.assertEqual(result["delete_candidates"][0]["title"], "Removed")
        self.assertNotIn("delete", [r["operation"] for r in result["entries"]])

    def test_remote_drift_for_unchanged_local(self):
        row = self.add()
        previous = self.state(row)
        self.baseline["entries"] = [previous]
        observation = dict(previous, exists=True, observed_at="2026-10-03T12:01:00Z", revision_id=102)
        entry = self.run_build([observation])["entries"][0]
        self.assertEqual(entry["operation"], "unchanged")
        self.assertEqual(entry["conflicts"], ["REMOTE_DRIFT"])

    def test_stored_text_without_single_final_lf_does_not_queue_a_resave(self):
        page = self.add()
        blank = self.add("blank", title="Blank paragraph", text="Example data\n\n")
        edit = self.add("edit", title="Edited page", text="Revised data\n")
        asset = self.add("asset", "assets", "File:Asset.png", 6, b"Example data\n", suffix=".png")
        self.baseline["entries"] = [self.state(row, b"Example data") for row in (page, blank, edit, asset)]
        observed = dict(self.baseline["entries"][0], exists=True, observed_at="2026-10-03T12:01:00Z",
                        revision_id=102)
        rows = {row["id"]: row for row in self.run_build([observed])["entries"]}
        self.assertEqual(rows["item"]["operation"], "unchanged")
        self.assertEqual(rows["item"]["conflicts"], ["REMOTE_DRIFT"])
        self.assertEqual(rows["item"]["content_hash"], digest(b"Example data\n"))
        self.assertEqual((self.output / rows["item"]["file"]).read_bytes(), b"Example data\n")
        for name in ("blank", "edit", "asset"):
            self.assertEqual(rows[name]["operation"], "update")

    def test_remote_hash_change_is_drift_even_if_revision_equal(self):
        row = self.add()
        previous = self.state(row)
        self.baseline["entries"] = [previous]
        observation = dict(previous, exists=True, observed_at="now", content_hash=digest(b"edited"))
        self.assertEqual(self.run_build([observation])["entries"][0]["conflicts"], ["REMOTE_DRIFT"])

    def test_remote_existing_without_baseline_is_not_blind_create(self):
        row = self.add()
        observation = dict(self.state(row), exists=True, observed_at="now")
        self.assertEqual(self.run_build([observation])["entries"][0]["conflicts"],
                         ["REMOTE_EXISTS_WITHOUT_BASELINE"])

    def test_remote_deleted_and_new_confirmed_absent(self):
        row = self.add()
        self.baseline["entries"] = [self.state(row)]
        new = self.add("new", title="New")
        observations = [{"title": r["title"], "namespace": 0, "exists": False, "observed_at": "now"}
                        for r in (row, new)]
        entries = {r["id"]: r for r in self.run_build(observations)["entries"]}
        self.assertEqual(entries["item"]["conflicts"], ["REMOTE_DELETED"])
        self.assertEqual(entries["new"]["conflicts"], [])

    def test_matching_snapshot_and_baseline(self):
        row = self.add()
        previous = self.state(row)
        self.baseline["entries"] = [previous]
        observation = dict(previous, exists=True, observed_at="now")
        self.assertEqual(self.run_build([observation])["entries"][0]["conflicts"], [])

    def test_asset_version_change_is_drift(self):
        row = self.add("image", "assets", "File:Item.png", 6, b"image", suffix=".png")
        previous = self.state(row)
        self.baseline["entries"] = [previous]
        observation = dict(previous, exists=True, observed_at="now", file_revision="upload-version-2")
        self.assertEqual(self.run_build([observation])["entries"][0]["conflicts"], ["REMOTE_DRIFT"])

    def test_receipt_path_migration_preserves_publish_decisions(self):
        page = self.add()
        asset = self.add("image", "assets", "File:Item.png", 6, b"image", suffix=".png")
        self.baseline["entries"] = [dict(self.state(row), receipt="dist/old/receipt.json")
                                    for row in (page, asset)]
        before = self.run_build()
        for row in self.baseline["entries"]:
            row["receipt"] = "publishing/history/receipt.json"
        self.output = self.root / "dist" / "after"
        after = self.run_build()
        self.assertEqual(before["entries"], after["entries"])
        self.assertEqual(before["delete_candidates"], after["delete_candidates"])
        self.assertTrue(all(row["operation"] == "unchanged" for row in after["entries"]))
        self.assertTrue(all(row["conflicts"] == ["REMOTE_UNVERIFIED"] for row in after["entries"]))
        ManualPublisher().prepare(self.output)
        validation = json.loads((self.output / "validation.json").read_text(encoding="utf8"))
        self.assertFalse(validation["production_approved"])

    def test_repository_baseline_receipts_are_available(self):
        root = Path(__file__).resolve().parents[1]
        baseline = json.loads((root / "publishing/baseline.json").read_text(encoding="utf8"))
        receipts = {row["receipt"] for row in baseline["entries"] if "receipt" in row}
        self.assertTrue(receipts)
        for relative in receipts:
            with self.subTest(receipt=relative):
                path = root / relative
                self.assertTrue(path.resolve().is_relative_to((root / "publishing/history").resolve()))
                self.assertTrue(path.is_file())
                self.assertFalse(path.is_symlink())
                json.loads(path.read_text(encoding="utf8"))

    def test_reject_unsafe_or_incomplete_source_before_export(self):
        original = self.add()
        cases = [dict(original, source="../private.wiki"), dict(original, title="Template:Item"),
                 dict(original, namespace=10), dict(original, ownership="mixed"),
                 dict(original, change_reason=""), dict(original, generator=""),
                 dict(original, asset_relationships=["missing"])]
        for row in cases:
            with self.subTest(row=row):
                self.registry["entries"] = [row]
                with self.assertRaises(ValueError):
                    self.run_build()
                self.assertFalse(self.output.exists())

    def test_namespace_alias_collision(self):
        self.registry["namespace_prefixes"]["10"].append("模板")
        self.add("first", "templates", "Template:Example_item", 10)
        self.add("second", "templates", "模板:Example item", 10)
        with self.assertRaises(ValueError):
            self.run_build()

    def test_wrong_target_baseline_fails(self):
        self.add()
        self.baseline["target"] = "another-wiki"
        with self.assertRaises(ValueError):
            self.run_build()

    def test_source_crlf_rejected(self):
        self.add(text="a\r\nb\r\n")
        with self.assertRaises(ValueError):
            self.run_build()

    def test_artifact_tampering_rejected(self):
        self.add()
        manifest = self.run_build()
        (self.output / manifest["entries"][0]["file"]).write_bytes(b"tampered")
        with self.assertRaises(ValueError):
            ManualPublisher().prepare(self.output)

    def test_extra_file_rejected(self):
        self.run_build()
        (self.output / "unregistered.txt").write_text("extra", encoding="utf-8")
        with self.assertRaises(ValueError):
            verify_bundle(self.output)

    def test_manifest_and_report_tampering_rejected(self):
        self.run_build()
        for name in ("manifest.json", "publish-report.md"):
            path = self.output / name
            original = path.read_bytes()
            with self.subTest(file=name):
                path.write_bytes(original + b" ")
                with self.assertRaises(ValueError):
                    verify_bundle(self.output)
                path.write_bytes(original)

    def test_no_overwriting_review_bundle_or_publishing(self):
        self.run_build()
        original = (self.output / "manifest.json").read_bytes()
        with self.assertRaises(ValueError):
            self.run_build()
        self.assertEqual((self.output / "manifest.json").read_bytes(), original)
        with self.assertRaises(RuntimeError):
            ManualPublisher().publish(self.output, self.root / "approval.json")

    def test_api_mode_fails_before_export(self):
        self.registry["mode"] = "MEDIAWIKI_API"
        with self.assertRaises(ValueError):
            self.run_build()
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
