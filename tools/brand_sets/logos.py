from html import escape
from urllib.parse import quote


def image_html(filename, label):
    return ('<span class="td2-logo-art">'
            '<img data-brand-file="' + escape(filename, quote=True) + '" src="images/'
            + quote(filename) + '" alt="' + escape(label, quote=True) + '"></span>')


def source():
    from .build import HEADER
    image = '<span class="td2-logo-art">[[File:{{{文件}}}|link=|alt={{{名称|}}}]]</span>'
    return (HEADER + '<noinclude>信息卡 Logo 按原始像素尺寸显示，保留原图透明留白和文件地址。参数：文件、名称。'
            '</noinclude><includeonly>{{#if:{{{文件|}}}|'
            + image + '}}</includeonly>\n')
