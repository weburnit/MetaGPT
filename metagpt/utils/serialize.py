#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Desc   : the implement of serialization and deserialization

import copy
import pickle

from metagpt.utils.common import import_class


def resolve_reference(schema: dict, ref: str) -> dict:
    """
    Resolve the given reference in the schema to its definition.

    :param schema: The full schema dictionary.
    :param ref: The reference string to resolve.
    :return: The resolved schema definition.
    """
    # Strip the leading '#' from the ref and split the path
    ref_path = ref.lstrip('#/').split('/')
    ref_obj = schema
    for path in ref_path:
        ref_obj = ref_obj[path]
    return ref_obj


def get_python_type(schema_property: dict, schema: dict) -> tuple:
    """
    Given a schema property, return the corresponding Python type as a tuple.

    :param schema_property: The schema property to convert.
    :param schema: The full schema dictionary.
    :return: A tuple containing the Python type and ellipsis to indicate any value.
    """
    property_type = schema_property.get('type', None)

    if property_type == 'string':
        return (str, ...)
    elif property_type == 'array':
        # Check if there is a reference to another schema definition
        items_ref = schema_property["items"].get('$ref')
        if items_ref:
            # Resolve the reference
            items_schema = resolve_reference(schema, items_ref)
            # Get the Python type for the resolved schema
            return (list, [get_python_type(items_schema, schema)])
        elif schema_property["items"]["type"] == 'string':
            return (list, [str])
        # Extend here with more types if necessary
    elif property_type == 'object':
        if 'properties' not in schema_property:
            return (dict, ...)
        # Map each property in the object to its corresponding Python type
        return (dict, {key: get_python_type(value, schema) for key, value in schema_property["properties"].items()})
    # Extend here with more types if necessary

    # Fallback for types not explicitly handled
    return (object, ...)


def actionoutout_schema_to_mapping(schema: dict) -> dict:
    """
    Generate a mapping from schema to Python types, including handling of $refs.

    :param schema: The JSON schema as a dictionary.
    :return: A dictionary mapping field names to Python types.
    """
    mapping = dict()
    for field, property in schema["properties"].items():
        # Check if the property has a $ref to another definition
        if '$ref' in property:
            # Resolve the reference
            ref_schema = resolve_reference(schema, property['$ref'])
            # Get the Python type for the resolved schema
            mapping[field] = get_python_type(ref_schema, schema)
        else:
            # Directly get the Python type for the property
            mapping[field] = get_python_type(property, schema)
    return mapping


def actionoutput_mapping_to_str(mapping: dict) -> dict:
    new_mapping = {}
    for key, value in mapping.items():
        new_mapping[key] = str(value)
    return new_mapping


def actionoutput_str_to_mapping(mapping: dict) -> dict:
    new_mapping = {}
    for key, value in mapping.items():
        if value == "(<class 'str'>, Ellipsis)":
            new_mapping[key] = (str, ...)
        else:
            new_mapping[key] = eval(value)  # `"'(list[str], Ellipsis)"` to `(list[str], ...)`
    return new_mapping


def serialize_message(message: "Message"):
    message_cp = copy.deepcopy(message)  # avoid `instruct_content` value update by reference
    ic = message_cp.instruct_content
    if ic:
        # model create by pydantic create_model like `pydantic.main.prd`, can't pickle.dump directly
        schema = ic.model_json_schema()
        mapping = actionoutout_schema_to_mapping(schema)

        message_cp.instruct_content = {"class": schema["title"], "mapping": mapping, "value": ic.model_dump()}
    msg_ser = pickle.dumps(message_cp)

    return msg_ser


def deserialize_message(message_ser: str) -> "Message":
    message = pickle.loads(message_ser)
    if message.instruct_content:
        ic = message.instruct_content
        actionnode_class = import_class("ActionNode", "metagpt.actions.action_node")  # avoid circular import
        ic_obj = actionnode_class.create_model_class(class_name=ic["class"], mapping=ic["mapping"])
        ic_new = ic_obj(**ic["value"])
        message.instruct_content = ic_new

    return message
