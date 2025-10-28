from dataclasses import dataclass
from enum import Enum, auto
import re
from typing import Dict, List, Optional

import tree_sitter_cpp
import tree_sitter_jsdoc
from tree_sitter import Language, Node, Parser

TAB = "    "

# We use JSDoc since it is available on PyPI and has similar syntax
DOXYGEN_LANGUAGE = Language(tree_sitter_jsdoc.language(), "doxygen")
CPP_LANGUAGE = Language(tree_sitter_cpp.language(), "cpp")

# Initialize parser
cpp_parser = Parser()
cpp_parser.set_language(CPP_LANGUAGE)  # Needed in 0.21

doxygen_parser = Parser()
doxygen_parser.set_language(DOXYGEN_LANGUAGE)


class_query = CPP_LANGUAGE.query("""
((comment) @comment
    .
    (class_specifier
        name: (type_identifier) @name
        body: (field_declaration_list)
        ) @class
        )
""")

method_query = CPP_LANGUAGE.query("""
((comment) @comment
    .
    (field_declaration
        (storage_class_specifier)? @storage_class
        declarator: (function_declarator
            declarator: (field_identifier) @name
            parameters: (parameter_list)? @parameters
        )
        ))
""")

free_function_query = CPP_LANGUAGE.query("""
((translation_unit
(comment) @comment
 .
 (declaration
     (storage_class_specifier)? @storage_class
     declarator: (function_declarator
         declarator: (identifier) @name
         parameters: (parameter_list)? @parameters
     )
    )))
""")

constructor_query = CPP_LANGUAGE.query("""
((field_declaration_list
  (comment) @comment
   .
   (declaration
       (storage_class_specifier)? @storage_class
       declarator: (function_declarator
           declarator: (identifier) @name
           parameters: (parameter_list)? @parameters
       ))
    ))
    """)

# Unfortunately, tree-sitter does not allow node type alternations
parameter_query = CPP_LANGUAGE.query("""
([(parameter_declaration
	[(qualified_identifier) (primitive_type) (type_identifier) (template_type)] @type
	[(reference_declarator) (pointer_declarator) (identifier)]? @identifier
)
(optional_parameter_declaration
	[(qualified_identifier) (primitive_type) (type_identifier) (template_type)] @type
	[(reference_declarator) (pointer_declarator) (identifier)]? @identifier
    default_value: (_) @default_value
)])
""")


# @dataclass
# class FunctionParam:
#     name: str
#     doc: str


@dataclass
class FunctionDoxygen:
    should_bind: bool
    py_name: str
    brief: str
    dox_params: List[tuple[str, str]]
    dox_ret: str
    nb_dict: str

    @classmethod
    def parse(cls, doxygen_node_unparsed: Node, cpp_name: str) -> "FunctionDoxygen":
        """Parse a function's doxygen comment."""
        should_bind = False
        brief = ""
        py_name = cpp_name
        dox_params: List[tuple[str, str]] = []
        dox_ret = ""
        nb_dict = ""

        doxygen_node = doxygen_parser.parse(doxygen_node_unparsed.text).root_node

        for n in doxygen_node.children:
            match n.type:
                case "description":
                    brief = n.text.decode("utf-8").replace("*", "").replace("\n", "\\n")
                case "tag":
                    match n.children[0].text.decode("utf-8"):
                        case "@param":
                            if len(n.children) < 3:
                                raise RuntimeError(
                                    f"Missing parameter description for {n.children[1].text.decode('utf-8')} in {cpp_name}"
                                )
                            dox_params.append(
                                (
                                    n.children[1].text.decode("utf-8"),
                                    n.children[2]
                                    .text.decode("utf-8")
                                    .replace("*", "")
                                    .replace("\n", "\\n"),
                                )
                            )
                        case "@return":
                            dox_ret = (
                                n.children[1]
                                .text.decode("utf-8")
                                .replace("*", "")
                                .replace("\n", "\\n")
                            )
                        case "@nb":
                            should_bind = True
                            if len(n.children) > 1:
                                nb_dict = n.children[1].text.decode("utf-8")

        return cls(should_bind, py_name, brief, dox_params, dox_ret, nb_dict)

    def gen_docstring(self) -> str:
        doc = ""
        doc += self.brief

        if self.dox_params:
            params_text = [f"{i}: {d}" for (i, d) in self.dox_params]
            doc += r"\n\nArgs:\n" + TAB + (r"\n" + TAB).join(params_text)

        if self.dox_ret:
            doc += r"\n\nReturns: " + self.dox_ret

        return doc


class BindingType(Enum):
    PLAIN = auto()
    STATIC = auto()
    INIT = auto()
    NEW = auto()
    OVERLOAD = auto()
    PROP_RO = auto()
    PROP_RW = auto()
    STATIC_PROP_RO = auto()
    STATIC_PROP_RW = auto()


@dataclass
class FunctionBinding:
    py_name: str
    cpp_declarations: List[Dict[str, Node]]
    doxygen: FunctionDoxygen
    binding_type: BindingType = BindingType.PLAIN
    extra: Optional[str] = ""


def build_function(
    function: FunctionBinding,
    class_name: Optional[str] = None,
) -> str:
    """Build a function or method declaration."""
    docstring = function.doxygen.gen_docstring()

    # Parse cpp declaration parameters.
    cpp_match = function.cpp_declarations[0]
    cpp_params: list[tuple[str, str, Optional[str]]] = []
    if "parameters" in function.cpp_declarations[0]:
        for param_match in parameter_query.matches(cpp_match["parameters"]):
            param_type = param_match[1]["type"].text.decode("utf-8")
            identifier = param_match[1]["identifier"].text.decode("utf-8")

            # Move reference or pointer declarator to type
            if identifier[0] in ["*", "&"]:
                param_type += " " + identifier[0]
                identifier = identifier[1:]

            # TODO(akoen): I think this can be removed
            if len(identifier_split := identifier.strip().split(" ")) > 1:
                print(identifier_split)
                raise AssertionError()
                param_type += identifier_split[0]
                identifier = identifier_split[1]

            cpp_params.append(
                (
                    param_type,
                    identifier,
                    param_match[1]["default_value"].text.decode("utf-8")
                    if "default_value" in param_match[1]
                    else None,
                )
            )

    params_text = ""
    for param in cpp_params:
        params_text += f', "{param[1]}"_a'

        if param[2]:
            params_text += f" = {param[2]}"

    cpp_names = [f["name"].text.decode("utf-8") for f in function.cpp_declarations]

    def_fn = {
        BindingType.PLAIN: "def",
        BindingType.STATIC: "def_static",
        BindingType.INIT: "def",
        BindingType.NEW: "def",
        BindingType.OVERLOAD: "def",
        BindingType.PROP_RO: "def_prop_ro",
        BindingType.PROP_RW: "def_prop_rw",
        BindingType.STATIC_PROP_RO: "def_prop_ro_static",
        BindingType.STATIC_PROP_RW: "def_prop_rw_static",
    }[function.binding_type]

    ref = ", ".join(
        [
            "&" + (class_name + "::" if class_name else "") + cpp_name
            for cpp_name in cpp_names
        ]
    )

    template_params = ", ".join([p[0] for p in cpp_params])

    extra = ", " + function.extra if function.extra else ""

    # Constructors
    # .def(nb::init<const std::string &>())
    if function.binding_type == BindingType.INIT:
        return f'.{def_fn}(nb::init<{template_params}>(){params_text}, "{docstring}"{extra})'

    # Custom constructors
    if function.binding_type == BindingType.NEW:
        return f'.{def_fn}(nb::new_({ref}){params_text}, "{docstring}"{extra})'

    # Overloads
    # .def("set", nb::overload_cast<int>(&Pet::set), "Set the pet's age")
    if function.binding_type == BindingType.OVERLOAD:
        ref = f"nb::overload_cast<{template_params}>({ref})"

    return f'.{def_fn}("{function.py_name}", {ref}{params_text}, "{docstring}"{extra})'


query_class_comment = DOXYGEN_LANGUAGE.query("""
(tag
    (tag_name) @tag_name
    (identifier)? @identifier
    (description)? @description
    (type)? @type
) """)

func_doc_brief_query = DOXYGEN_LANGUAGE.query("""
((description) @description)
""")


def parse_nb_dict(nb_dict: str) -> dict[str, str]:
    """Parse an @nb dict.

    Format is * @nb key: value, key, key: 'valu,e', ...

    Args:
        nb_dict: The nb dict

    Returns:
        parsed dictionary
    """
    # Match a key-value pair of form key1: value, key2, key3: value
    # , in value can be escaped with single quotes

    nb_dict_pattern = r"(\w+)(?::\s*((?:(?:'[^']*')|[^,])+))?"

    nb_dict_matches = re.findall(nb_dict_pattern, nb_dict)

    nb_dict_parsed: Dict[str, Optional[str]] = {}

    for match in nb_dict_matches:
        if len(match) == 2:
            nb_dict_parsed[match[0]] = match[1].strip(" '")
        else:
            nb_dict_parsed[match[0]] = None

    return nb_dict_parsed


def build_functions(node: Node, class_name: Optional[str]) -> list[str]:
    functions: list[FunctionBinding] = []

    matches = (
        constructor_query.matches(node) + method_query.matches(node)
        if class_name
        else free_function_query.matches(node)
    )

    for match in matches:
        cpp_name = match[1]["name"].text.decode("utf-8")
        function_doxygen = FunctionDoxygen.parse(match[1]["comment"], cpp_name)

        if not function_doxygen.should_bind:
            continue

        py_names = [m.py_name for m in functions]

        nb_dict_parsed = parse_nb_dict(function_doxygen.nb_dict)

        function = FunctionBinding(
            cpp_name, [match[1]], function_doxygen, BindingType.PLAIN
        )

        # Check if method is static
        is_static = False
        if "storage_class" in match[1]:
            storage_class = match[1]["storage_class"].text.decode("utf-8")
            if storage_class == "static":
                is_static = True
                function.binding_type = BindingType.STATIC

        if cpp_name == class_name:
            function.binding_type = BindingType.INIT

        elif "new" in nb_dict_parsed:
            function.binding_type = BindingType.NEW

        elif "name" in nb_dict_parsed:
            function.py_name = nb_dict_parsed["name"]

        if "extra" in nb_dict_parsed:
            function.extra = nb_dict_parsed["extra"].strip("'")

        if "prop_r" in nb_dict_parsed:
            py_name_parsed = nb_dict_parsed["prop_r"]
            if py_name_parsed in py_names:
                i = py_names.index(py_name_parsed)
                functions[i].cpp_declarations.insert(0, match[1])
                function = None
            else:
                function.py_name = py_name_parsed
                function.binding_type = (
                    BindingType.STATIC_PROP_RO if is_static else BindingType.PROP_RO
                )

        elif "prop_w" in nb_dict_parsed:
            py_name_parsed = nb_dict_parsed["prop_w"]
            if py_name_parsed in py_names:
                i = py_names.index(py_name_parsed)
                function = None
                functions[i].cpp_declarations.append(match[1])
                functions[i].binding_type = (
                    BindingType.STATIC_PROP_RW if is_static else BindingType.PROP_RW
                )
            else:
                function.py_name = py_name_parsed
                function.binding_type = (
                    BindingType.STATIC_PROP_RW if is_static else BindingType.PROP_RW
                )
        # Overload
        elif function.py_name in py_names and function.binding_type != BindingType.INIT:
            i = py_names.index(function.py_name)
            functions[i].binding_type = BindingType.OVERLOAD
            function.binding_type = BindingType.OVERLOAD

        if function:
            functions.append(function)

    fn_defs = [build_function(method, class_name) for method in functions]

    return fn_defs


def generate_classes(node: Node) -> str:
    classes: List[str] = []

    for match in class_query.matches(node):
        class_name = match[1]["name"].text.decode("utf-8")
        class_hierarchy = [class_name]

        should_bind = False
        nb_dict = ""

        comment = match[1]["comment"]
        doxygen_node = doxygen_parser.parse(comment.text).root_node

        for n in doxygen_node.children:
            match n.type:
                case "tag":
                    match n.children[0].text.decode("utf-8"):
                        case "@nb":
                            should_bind = True
                            if len(n.children) > 1:
                                nb_dict = n.children[1].text.decode("utf-8")

        if not should_bind:
            continue

        nb_dict_parsed = parse_nb_dict(nb_dict)

        if "inherit" in nb_dict_parsed:
            class_hierarchy.append(nb_dict_parsed["inherit"])

        extra = ""
        if "extra" in nb_dict_parsed:
            extra = ", " + nb_dict_parsed["extra"]

        class_output = (
            TAB + f'nb::class_<{", ".join(class_hierarchy)}>(m, "{class_name}"{extra})'
        )

        fn_defs = build_functions(match[1]["class"], class_name)
        fn_defs = ["\n" + 2 * TAB + fn_def for fn_def in fn_defs]
        class_output += "".join(fn_defs) + ";"

        classes.append(class_output)

    return "\n\n".join(classes)


def generate_free_functions(node: Node) -> str:
    fn_defs = build_functions(node, None)
    fn_defs = [TAB + "m" + fn_def + ";" for fn_def in fn_defs]

    output = f"\n\n".join(fn_defs)
    return output


def generate_enums(node: Node) -> str:
    enum_query = CPP_LANGUAGE.query("""((comment) @comment
                            .
                          (enum_specifier
                            name: (type_identifier) @name
                            body: (enumerator_list
                                    (enumerator)+)
                                    @enum_list))""")

    matches = enum_query.matches(node)
    enums = []
    for match in matches:
        should_bind = False
        nb_dict = ""

        comment = match[1]["comment"]
        doxygen_node = doxygen_parser.parse(comment.text).root_node

        for n in doxygen_node.children:
            match n.type:
                case "tag":
                    match n.children[0].text.decode("utf-8"):
                        case "@nb":
                            should_bind = True
                            if len(n.children) > 1:
                                nb_dict = n.children[1].text.decode("utf-8")

        if not should_bind:
            continue

        nb_dict_parsed = parse_nb_dict(nb_dict)

        name = match[1]["name"].text.decode("utf-8")
        enumerators: list[tuple[str, str]] = []
        enumerator_nodes = [
            e for e in match[1]["enum_list"].children if e.type == "enumerator"
        ]
        for enumerator_node in enumerator_nodes:
            entry_name = enumerator_node.children[0].text.decode("utf-8")
            value = (
                enumerator_node.children[1].text.decode("utf-8")
                if len(enumerator_node.children) == 2
                else "auto()"
            )
            enumerators.append((entry_name, value))

        enums.append(
            f'{TAB}nb::enum_<{name}>(m, "{name}")'
            + "".join(
                f'\n{TAB}{TAB}.value("{n}", {name}::{n})' for (n, v) in enumerators
            )
            + ";"
        )

    return "\n\n".join(enums)


def build_header(header_name: str, source_code: str) -> str:
    tree = cpp_parser.parse(bytes(source_code, "utf8"))

    classes = generate_classes(tree.root_node)
    free_functions = generate_free_functions(tree.root_node)
    enums = generate_enums(tree.root_node)

    return f"""#pragma once
// This file was autogenerated. Do not edit. //
#include "{header_name}.h"

void bind_{header_name.lower()}(nb::module_ &m)
{{
    // Enums
{enums}

    // Classes
{classes}

    // Functions
{free_functions}

}};
"""
