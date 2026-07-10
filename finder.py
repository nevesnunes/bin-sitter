#!/usr/bin/env python3

from dataclasses import dataclass
from typing import Dict, List, Set
import ast
import sys

from logger import logger


@dataclass(unsafe_hash=True, order=True, frozen=True)
class FieldAssignment:
    func: str
    prop: bool
    lhs: str
    rhs: str


class FieldAssignmentFinder(ast.NodeVisitor):
    def __init__(self):
        self.classes: List[str] = []
        self.matches: Dict[str, Set] = {}
        self.matched_names: Dict[str, set] = {}
        self.matched_t_attrs: Set[str] = set()
        self.seq_fields: Set[str] = set()

    def from_source_str(self, source: str):
        self.matches.clear()
        self.visit(ast.parse(source, "_"))

    def visit_ClassDef(self, node: ast.ClassDef):
        for stmt in node.body:
            if (
                isinstance(stmt, ast.Assign)
                and len(stmt.targets) == 1
                and isinstance(stmt.targets[0], ast.Name)
                and stmt.targets[0].id == "SEQ_FIELDS"
                and isinstance(stmt.value, ast.List)
            ):
                self.seq_fields.clear()
                for elt in stmt.value.elts:
                    if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                        self.seq_fields.add(elt.value)

        self.classes.append(node.name)
        self.generic_visit(node)
        self.classes.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef):
        self._check_function(node)
        self.generic_visit(node)

    def _check_function(self, node):
        is_prop = self._is_property(node)
        if not (is_prop or self._is_read_call(node)):
            return

        # First pass: collect variables assigned a class instantiation.
        instantiated_vars = {}
        instantiated_var_names = {}
        for child in ast.walk(node):
            if (
                isinstance(child, ast.Assign)
                and len(child.targets) == 1
                and isinstance(child.targets[0], ast.Name)
                and self._is_class_instantiation(child.value)
            ):
                instantiated_vars[child.targets[0].id] = child.value
                instantiated_var_names[child.targets[0].id] = self._val(
                    child.value.func
                )

        # Second pass: find direct assignments or appended variables.
        for child in ast.walk(node):
            if isinstance(child, ast.Assign):
                self._check_assignment(node, child, is_prop, instantiated_vars)
            elif isinstance(child, ast.AnnAssign) or isinstance(child, ast.AugAssign):
                self._check_single_target_assignment(
                    node, child, is_prop, instantiated_vars
                )
            elif isinstance(child, ast.Call):
                self._check_append_call(node, child, is_prop, instantiated_var_names)

    def _is_property(self, node):
        for decorator in node.decorator_list:
            if self._val(decorator) == "property":
                return True
        return False

    def _is_read_call(self, node):
        # Include endianness choices: `_read_le()`, `_read_be()`.
        return node.name.startswith("_read")

    def _check_assignment(self, func, assign: ast.Assign, is_prop: bool, seen_vars):
        is_store_class_instantiation = self._is_self_field(
            assign.targets
        ) and self._is_class_instantiation(assign.value)
        is_store_at_property_field = self._is_self_field_by_name(
            assign.targets, func.name
        )
        if is_store_class_instantiation or is_store_at_property_field:
            target = next(filter(self._is_self_attribute, assign.targets))
            while isinstance(target, ast.Subscript):
                target = target.value
            clazz = self.classes[-1]
            if clazz not in self.matches:
                self.matches[clazz] = set()

            assign_val = assign.value
            assign_val_name = self._val_or(assign_val, None)
            if assign_val_name in seen_vars:
                assign_val = seen_vars[assign_val_name]
            is_call = isinstance(assign_val, ast.Call)
            if self._is_attribute(assign.value, func.name):
                self.matched_t_attrs.add(func.name)
            if not (func.name in self.matched_names) or is_call:
                logger.debug(target.attr, assign_val_name, assign_val, is_call, seen_vars)
                self.matches[clazz].add(
                    FieldAssignment(
                        func.name,
                        is_prop,
                        self._val(target),
                        self._val(
                            f"<{assign_val.__class__.__name__}>"
                            if not is_call
                            else assign_val.func
                        ),
                    )
                )
                self.matched_names[func.name] = is_call

    def _check_single_target_assignment(self, func, assign, is_prop: bool, seen_vars):
        is_store_class_instantiation = self._is_self_attribute(
            assign.target
        ) and self._is_class_instantiation(assign.value)
        is_store_at_property_field = self._is_self_attribute_by_name(
            assign.target, func.name
        )
        if is_store_class_instantiation or is_store_at_property_field:
            target = assign.target
            while isinstance(target, ast.Subscript):
                target = target.value
            clazz = self.classes[-1]
            if clazz not in self.matches:
                self.matches[clazz] = set()

            assign_val = assign.value
            assign_val_name = self._val_or(assign_val, None)
            if assign_val_name in seen_vars:
                assign_val = seen_vars[assign_val_name]
            is_call = isinstance(assign_val, ast.Call)
            if self._is_attribute(assign.value, func.name):
                self.matched_t_attrs.add(func.name)
            if not (func.name in self.matched_names) or is_call:
                logger.debug(target.attr, assign_val_name, assign_val, is_call, seen_vars)
                self.matches[clazz].add(
                    FieldAssignment(
                        func.name,
                        is_prop,
                        self._val(target),
                        self._val(
                            f"<{assign_val.__class__.__name__}>"
                            if not is_call
                            else assign_val.func
                        ),
                    )
                )
                self.matched_names[func.name] = is_call

    def _check_append_call(
        self, func, call: ast.Call, is_prop: bool, instantiated_vars
    ):
        # Match append(...)
        if not (isinstance(call.func, ast.Attribute) and call.func.attr == "append"):
            return

        # Match self.foo.append(...)
        receiver = call.func.value
        if not (
            isinstance(receiver, ast.Attribute)
            and isinstance(receiver.value, ast.Name)
            and receiver.value.id == "self"
            and len(call.args) == 1
        ):
            return

        arg = call.args[0]
        if isinstance(arg, ast.Name) and arg.id in instantiated_vars:
            logger.debug(f"self.{receiver.attr}.append({arg.id}: {instantiated_vars[arg.id]})")
            clazz = self.classes[-1]
            if clazz not in self.matches:
                self.matches[clazz] = set()
            self.matches[clazz].add(
                FieldAssignment(
                    self._val(func.name),
                    is_prop,
                    receiver.attr,
                    instantiated_vars[arg.id],
                )
            )

    def _is_attribute(self, node, func_name):
        while isinstance(node, ast.Subscript):
            node = node.value
        return isinstance(node, ast.Name) and node.id == f"_t__m_{func_name}"

    def _is_self_field(self, targets):
        return any(self._is_self_attribute(t) for t in targets)

    def _is_self_attribute(self, node):
        while isinstance(node, ast.Subscript):
            node = node.value
        return (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "self"
            and node.attr != "_debug"
        )

    def _is_self_field_by_name(self, targets, func_name):
        return any(self._is_self_attribute_by_name(t, func_name) for t in targets)

    def _is_self_attribute_by_name(self, node, func_name):
        while isinstance(node, ast.Subscript):
            node = node.value
        return self._is_self_attribute(node) and (
            node.attr == f"_m_{func_name}" or node.attr in self.seq_fields
        )

    def _is_class_instantiation(self, node):
        if not isinstance(node, ast.Call):
            return False

        # Match Foo(...)
        if isinstance(node.func, ast.Name):
            return True

        # Match module.Foo(...)
        if isinstance(node.func, ast.Attribute):
            return True

        return False

    def _val_or(self, node, default):
        try:
            return self._val(node)
        except Exception as e:
            logger.debug(e)
            return default

    def _val(self, node):
        if isinstance(node, ast.Attribute):
            return node.attr

        if isinstance(node, ast.Name):
            return node.id

        if isinstance(node, ast.Subscript):
            return self._val(node.value)

        if isinstance(node, list) and len(node) > 0:
            return self._val(node[0])

        if isinstance(node, str):
            return node

        raise RuntimeError(f"Unsupported node '{node}': '{node.__class__}'")
