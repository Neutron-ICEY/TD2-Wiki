"""装备次属性领域入口；不读取Bonus目录或加成数值规则。"""
from tools.publish.bundle import require
from tools.identity import read_json
from .model import validate_catalog_records

EMPTY = {"schema_version": 2, "attributes": []}
def validate_catalog(catalog, icons):
    return validate_catalog_records(catalog, icons, "minor_attribute_", distinct_units=True)
def load_catalog(root):
    catalog = read_json(root / "data/brand-sets/minor-attributes.json")
    from tools.equipment_attributes.catalog import identity, load
    if (root / 'data/equipment/attributes.json').is_file():
        shared=load(root)
        catalog['attributes']=[identity(row,shared) for row in catalog['attributes']]
    validate_catalog(catalog, read_json(root / "data/brand-sets/category-icons.json"))
    return catalog
def by_id(catalog):
    rows = catalog["attributes"]
    require(all(r["id"].startswith("minor_attribute_") for r in rows), "次属性目录只接受 minor_attribute_ ID")
    return {r["id"]: r for r in rows}
