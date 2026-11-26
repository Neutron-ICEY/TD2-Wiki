from tools.equipment.wikitext import WikiSubset as Reader

class WikiSubset(Reader):
    def template(self,name,params):
        """Give isolated component fixtures a real rule identity; full pages resolve their own mapping."""
        fixtures={'品牌套装内容':'set:4cdce5b25c405137000321f5482f6f7b','装备组内容':'set:4cdce5b25bc1f2cc0002efead01ec184'}
        if name in fixtures:params={'资料ID':fixtures[name],**params}
        return super().template(name,params)
