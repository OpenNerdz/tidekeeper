from typing import get_args, get_origin, List
from aigpy.dictHelper import DictTool
from aigpy.modelHelper import __isDictList__, __isDict__

# Direct replacement for aigpy.model.dictToModel. Performs additional checks compared to the upstream implementation to handle List[Model] attributes.
def dictToModel(indict, model):
    if indict is None or model is None:
        return None
    ret = model
    maps = DictTool(indict)

    members = [attr for attr in dir(ret) if not callable(getattr(model, attr)) and not attr.startswith("_")]

    for key in members:
        if key.lower() not in maps:
            if __isObject__(getattr(ret, key)):
                setattr(ret, key, None)
            continue

        lvalue = maps[key.lower()]
        if __isDictList__(lvalue):
            current_value = getattr(ret, key)
            annotation = getattr(ret.__class__, "__annotations__", {}).get(key)
            if annotation and get_origin(annotation) in (list, List):
                item_type = get_args(annotation)[0]
                value = [dictToModel(item, item_type()) for item in lvalue]
            else:
                value = dictListToModelList(lvalue, getattr(ret, key))

        elif __isDict__(lvalue):
            value = dictToModel(lvalue, getattr(ret, key))
        else:
            value = lvalue

        setattr(ret, key, value)
    return ret
