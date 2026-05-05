"""tree-sitter parsing → IR. Owns all tree-sitter language/parser setup."""

import tree_sitter_cpp
import tree_sitter_jsdoc
from tree_sitter import Language, Node, Parser, Tree

from .ir import ClassIR, DocIR, EnumIR, EnumValueIR, FreeFunctionIR, HeaderIR, MethodIR, Param, SourceLoc, TagSet
from .tags import TAG_SCHEMA

CPP_LANGUAGE = Language(tree_sitter_cpp.language(), "cpp")
DOXYGEN_LANGUAGE = Language(tree_sitter_jsdoc.language(), "doxygen")

_cpp_parser = Parser()
_cpp_parser.set_language(CPP_LANGUAGE)

_doxygen_parser = Parser()
_doxygen_parser.set_language(DOXYGEN_LANGUAGE)


def parse_cpp(source: bytes) -> Tree:
    return _cpp_parser.parse(source)


def parse_doxygen(comment_text: bytes) -> Tree:
    return _doxygen_parser.parse(comment_text)


def _node_loc(node: Node, path: str) -> SourceLoc:
    line = node.start_point[0] + 1
    col = node.start_point[1] + 1
    return SourceLoc(path=path, line=line, col=col)


def _strip_continuation_prefix(text: str) -> str:
    """Strip leading ' * ' (Doxygen continuation marker) from each line.

    Strips exactly: ^[ \\t]*\\* ?  — leading whitespace, one '*', optionally
    one space. Asterisks elsewhere in the text are preserved.
    """
    out_lines = []
    for line in text.splitlines():
        i = 0
        n = len(line)
        while i < n and line[i] in " \t":
            i += 1
        if i < n and line[i] == "*":
            i += 1
            if i < n and line[i] == " ":
                i += 1
        out_lines.append(line[i:])
    return "\n".join(out_lines).strip()


def extract_tagset_from_comment(comment_node: Node, path: str) -> TagSet:
    """Parse a C++ comment node's text as Doxygen, extract all @nb_* tags.

    Classification (flag / value / repeated value) follows the TAG_SCHEMA arity.
    Unknown tags are stored as "once" values so validate.py can flag them.
    Every occurrence of every tag is recorded in `locations` (in source order)
    so validation can point at duplicates.
    """
    flags: set[str] = set()
    values: dict[str, str] = {}
    repeats: dict[str, list[str]] = {}
    locations: dict[str, list[SourceLoc]] = {}

    base_line = comment_node.start_point[0]  # 0-based line of comment start

    dox = parse_doxygen(comment_node.text).root_node
    for child in dox.children:
        if child.type != "tag":
            continue
        tag_name_node = child.children[0]
        tag_name = tag_name_node.text.decode("utf-8").lstrip("@")
        if not (tag_name == "nb" or tag_name.startswith("nb_")):
            continue

        tag_line = base_line + tag_name_node.start_point[0] + 1
        tag_col = tag_name_node.start_point[1] + 1
        loc = SourceLoc(path=path, line=tag_line, col=tag_col)
        locations.setdefault(tag_name, []).append(loc)

        body_parts = [c.text.decode("utf-8") for c in child.children[1:]]
        body = _strip_continuation_prefix(" ".join(body_parts).strip())

        schema_entry = TAG_SCHEMA.get(tag_name)
        if not body:
            flags.add(tag_name)
        elif schema_entry is not None and schema_entry.arity == "repeatable":
            repeats.setdefault(tag_name, []).append(body)
        else:
            # "once" tags and unknown tags both land here. Duplicates of a
            # "once" tag overwrite the previous body; this is an arity
            # violation that validate.py detects via len(locations[tag]) > 1.
            values[tag_name] = body

    return TagSet(
        flags=frozenset(flags),
        values=values,
        repeats={k: tuple(v) for k, v in repeats.items()},
        locations={k: tuple(v) for k, v in locations.items()},
    )


def _split_first_word(text: str) -> tuple[str, str]:
    """Split 'word rest of text' -> ('word', 'rest of text'). Strips."""
    text = text.strip()
    if not text:
        return ("", "")
    head, _, tail = text.partition(" ")
    return (head.strip(), tail.strip())


def _tag_body(child: Node) -> str:
    """Extract the body of a Doxygen tag node (everything after the tag_name)."""
    parts = [c.text.decode("utf-8") for c in child.children[1:]]
    return _strip_continuation_prefix(" ".join(parts).strip())


def extract_doc_from_comment(comment_node: Node) -> DocIR:
    """Extract Google-style DocIR from a Doxygen comment.

    Brief / detail are derived from @brief and free description text:
      - @brief present  -> brief = @brief, free description (if any) goes to detail.
      - @brief absent   -> brief = free description.

    @nb_doc is captured into DocIR.override (set to None when absent or empty).
    Downstream rendering decides whether the override replaces the generated
    docstring; this function does not collapse brief/detail when override is set.
    """
    description_parts: list[str] = []
    brief_tag: str | None = None
    detail_parts: list[str] = []
    params: list[tuple[str, str]] = []
    returns = ""
    raises: list[tuple[str, str]] = []
    override: str | None = None

    dox = parse_doxygen(comment_node.text).root_node
    for child in dox.children:
        if child.type == "description":
            description_parts.append(
                _strip_continuation_prefix(child.text.decode("utf-8"))
            )
        elif child.type == "tag":
            tag_name = child.children[0].text.decode("utf-8").lstrip("@")
            body = _tag_body(child)
            match tag_name:
                case "brief":
                    brief_tag = body
                case "param":
                    name, desc = _split_first_word(body)
                    if name:
                        params.append((name, desc))
                case "return" | "returns":
                    returns = body
                case "throws" | "raises" | "exception":
                    name, desc = _split_first_word(body)
                    if name:
                        raises.append((name, desc))
                case "nb_doc":
                    # An empty body means a bare `@nb_doc` flag, which is
                    # treated as "no override" rather than "override with
                    # empty string".
                    override = body or None

    free_description = "\n\n".join(p for p in description_parts if p).strip()

    if brief_tag is not None:
        brief = brief_tag
        if free_description:
            detail_parts.append(free_description)
    else:
        brief = free_description

    detail = "\n\n".join(detail_parts).strip()

    return DocIR(
        brief=brief,
        detail=detail,
        params=tuple(params),
        returns=returns,
        raises=tuple(raises),
        override=override,
    )


# Matches a Doxygen comment immediately followed by a non-template `class`
# definition with a body. Known gaps (intentional for now):
#   - struct (would need a separate (struct_specifier ...) alternation)
#   - template classes (template_declaration wraps class_specifier)
#   - nested classes (wrapped in field_declaration inside a body)
# Add support if production headers require it.
_CLASS_QUERY = CPP_LANGUAGE.query(
    """
    ((comment) @comment
     .
     (class_specifier
        name: (type_identifier) @name
        body: (field_declaration_list) @body))
    """
)


def parse_header(path: str, source: bytes) -> HeaderIR:
    tree = parse_cpp(source)
    classes = _parse_classes(tree.root_node, path)
    free_functions = _parse_free_functions(tree.root_node, path)
    enums = _parse_enums(tree.root_node, path)
    return HeaderIR(
        path=path,
        classes=classes,
        free_functions=free_functions,
        enums=enums,
    )


def _parse_classes(root: Node, path: str) -> tuple[ClassIR, ...]:
    out: list[ClassIR] = []
    for _match_id, captures in _CLASS_QUERY.matches(root):
        comment = captures["comment"]
        name_node = captures["name"]
        body_node = captures["body"]

        tags = extract_tagset_from_comment(comment, path)
        if "nb" not in tags.flags:
            continue

        doc = extract_doc_from_comment(comment)
        methods = _parse_methods(body_node, path)
        out.append(
            ClassIR(
                cpp_name=name_node.text.decode("utf-8"),
                loc=_node_loc(comment, path),
                tags=tags,
                doc=doc,
                methods=methods,
            )
        )
    return tuple(out)


# Field-declared method: virtual/normal members.
_METHOD_QUERY = CPP_LANGUAGE.query(
    """
    ((comment) @comment
     .
     (field_declaration
        (storage_class_specifier)? @storage_class
        declarator: (function_declarator
            declarator: (field_identifier) @name
            parameters: (parameter_list) @parameters)) @decl)
    """
)

# Constructor: declared as a `declaration` inside the field_declaration_list.
_CONSTRUCTOR_QUERY = CPP_LANGUAGE.query(
    """
    ((comment) @comment
     .
     (declaration
        (storage_class_specifier)? @storage_class
        declarator: (function_declarator
            declarator: (identifier) @name
            parameters: (parameter_list) @parameters)) @decl)
    """
)

# Parameter query.
# Type-side captures:
#   @qual — optional `const` / `volatile` / `restrict` qualifier on the type.
#   @type — the type name itself: `int`, `unsigned int`/`long long` (sized_type_specifier),
#           `std::string` (qualified_identifier), `T` (type_identifier),
#           `std::vector<int>` (template_type).
# Identifier-side captures:
#   @ident — the parameter identifier, possibly wrapped in a reference or
#            pointer declarator. The `&`/`*` is moved into the type by
#            _parse_params so the IR's `Param.type` is "int &" / "int *".
# Known gaps: function-pointer params, array params, ellipsis (`...`),
# template-template params. Add support if production headers need them.
_PARAMETER_QUERY = CPP_LANGUAGE.query(
    """
    ([(parameter_declaration
        (type_qualifier)? @qual
        [(qualified_identifier) (primitive_type) (sized_type_specifier)
         (type_identifier) (template_type)] @type
        [(reference_declarator) (pointer_declarator) (identifier)]? @ident)
      (optional_parameter_declaration
        (type_qualifier)? @qual
        [(qualified_identifier) (primitive_type) (sized_type_specifier)
         (type_identifier) (template_type)] @type
        [(reference_declarator) (pointer_declarator) (identifier)]? @ident
        default_value: (_) @default)])
    """
)


def _parse_methods(body_node: Node, path: str) -> tuple[MethodIR, ...]:
    out: list[MethodIR] = []
    for query in (_METHOD_QUERY, _CONSTRUCTOR_QUERY):
        for _id, caps in query.matches(body_node):
            comment = caps["comment"]
            tags = extract_tagset_from_comment(comment, path)
            if "nb" not in tags.flags:
                continue
            doc = extract_doc_from_comment(comment)
            name_node = caps["name"]
            params = _parse_params(caps["parameters"])
            is_static = "storage_class" in caps and (
                caps["storage_class"].text.decode("utf-8") == "static"
            )
            out.append(
                MethodIR(
                    cpp_name=name_node.text.decode("utf-8"),
                    loc=_node_loc(comment, path),
                    params=params,
                    is_cpp_static=is_static,
                    tags=tags,
                    doc=doc,
                )
            )
    # Sort by source order (start byte) since we ran two queries.
    out.sort(key=lambda m: (m.loc.line, m.loc.col))
    return tuple(out)


# Free functions declared at translation-unit scope. Known gaps (intentional):
#   - Functions inside `namespace ns { ... }` (body lives under declaration_list).
#   - Functions inside `extern "C" { ... }` (body lives under linkage_specification).
#   - Function templates (wrapped in template_declaration).
#   - Function definitions with inline bodies (function_definition, not declaration).
#   - Operator overloads (declarator is operator_name, not identifier).
# `@storage_class` is captured for query-shape symmetry with method/constructor
# queries; it is not consumed for free functions (no static-vs-instance split).
_FREE_FUNCTION_QUERY = CPP_LANGUAGE.query(
    """
    ((translation_unit
        (comment) @comment
        .
        (declaration
            (storage_class_specifier)? @storage_class
            declarator: (function_declarator
                declarator: (identifier) @name
                parameters: (parameter_list) @parameters))))
    """
)


def _parse_free_functions(root: Node, path: str) -> tuple[FreeFunctionIR, ...]:
    out: list[FreeFunctionIR] = []
    for _id, caps in _FREE_FUNCTION_QUERY.matches(root):
        comment = caps["comment"]
        tags = extract_tagset_from_comment(comment, path)
        if "nb" not in tags.flags:
            continue
        doc = extract_doc_from_comment(comment)
        name_node = caps["name"]
        params = _parse_params(caps["parameters"])
        out.append(
            FreeFunctionIR(
                cpp_name=name_node.text.decode("utf-8"),
                loc=_node_loc(comment, path),
                params=params,
                tags=tags,
                doc=doc,
            )
        )
    return tuple(out)


def _parse_params(parameter_list: Node) -> tuple[Param, ...]:
    out: list[Param] = []
    for _id, caps in _PARAMETER_QUERY.matches(parameter_list):
        param_type = caps["type"].text.decode("utf-8")
        if "qual" in caps:
            param_type = f"{caps['qual'].text.decode('utf-8')} {param_type}"
        ident = caps["ident"].text.decode("utf-8") if "ident" in caps else ""
        # Reference/pointer declarators carry the leading & or *.
        if ident and ident[0] in "*&":
            param_type = f"{param_type} {ident[0]}"
            ident = ident[1:]
        default = caps["default"].text.decode("utf-8") if "default" in caps else None
        out.append(Param(type=param_type, name=ident, default=default))
    return tuple(out)


# Top-level enum declarations. Known gaps (intentional for now):
#   - Anonymous enums (`enum { A };`): the query requires a name node.
#   - Nested enums declared inside a class body or namespace.
#   - Trailing `///<` Doxygen comments on enumerators (only leading comments
#     are attached as docstrings).
_ENUM_QUERY = CPP_LANGUAGE.query(
    """
    ((comment) @comment
     .
     (enum_specifier
        name: (type_identifier) @name
        body: (enumerator_list) @body))
    """
)


def _parse_enum_values(body_node: Node, path: str) -> tuple[EnumValueIR, ...]:
    """Walk enumerator_list children, attaching leading comments to enumerators."""
    out: list[EnumValueIR] = []
    pending_comment: Node | None = None
    for child in body_node.children:
        if child.type == "comment":
            pending_comment = child
            continue
        if child.type != "enumerator":
            pending_comment = None
            continue
        # tree-sitter-cpp exposes enumerator name and value via field accessors.
        # `value` is None for bare entries and any expression node for `A = expr`,
        # which is robust to bare-identifier RHS (`A = OTHER`) that a node-type
        # heuristic over children would miss.
        name_node = child.child_by_field_name("name") or child.children[0]
        value_node = child.child_by_field_name("value")

        doc = (
            extract_doc_from_comment(pending_comment)
            if pending_comment is not None
            else DocIR()
        )
        loc = _node_loc(pending_comment or child, path)
        out.append(
            EnumValueIR(
                cpp_name=name_node.text.decode("utf-8"),
                value=value_node.text.decode("utf-8") if value_node else None,
                doc=doc,
                loc=loc,
            )
        )
        pending_comment = None
    return tuple(out)


def _parse_enums(root: Node, path: str) -> tuple[EnumIR, ...]:
    out: list[EnumIR] = []
    for _id, caps in _ENUM_QUERY.matches(root):
        comment = caps["comment"]
        tags = extract_tagset_from_comment(comment, path)
        if "nb" not in tags.flags:
            continue
        doc = extract_doc_from_comment(comment)
        out.append(
            EnumIR(
                cpp_name=caps["name"].text.decode("utf-8"),
                loc=_node_loc(comment, path),
                tags=tags,
                doc=doc,
                values=_parse_enum_values(caps["body"], path),
            )
        )
    return tuple(out)
