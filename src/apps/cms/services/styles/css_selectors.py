"""Which classes does a stylesheet style on their own, in context, or as a hook?

Built on tinycss2's tokenizer, so quoted strings, escapes (``.md\\:hidden``), comments,
attribute selectors (``a[href$=".pdf"]``), ``@media`` / ``@supports`` / ``@layer``
blocks and nested rules are read the way a browser reads them.

Each selector is split at its combinators into compounds; the last one is the *subject*
(the element the rule styles), the others are *context*. A leading ``html``, ``body``
or ``:root`` followed by a space matches every element, so ``body .x`` counts as ``.x``.

* ``defined``: the class is the only class of the subject of a selector without context
  (``.x``, ``.x:hover``, ``a.x``, ``.x:not(.y)``). ``:is()``, ``:where()`` and
  ``:matches()`` pass their arguments through, so ``:is(.a, .b)`` defines both, while
  ``.a:is(.b)`` (like ``.a.b``) needs both classes and defines neither.
* ``context``: the class appears in a context compound: ``.event-page`` in
  ``.event-page .x``. The class is a hook other rules hang on.
* ``scoped``: every other appearance. The class is styled only inside another element
  (``.event-page .x``), only together with another class (``.btn.is-active``), only
  inside ``:not()`` / ``:has()`` / ``:nth-child(... of S)``, in a rule nested in another
  rule, or inside ``@scope``.

``defined`` wins over the other two; a class can be both ``context`` and ``scoped``.
"""

from dataclasses import dataclass, field

import tinycss2

PASS_THROUGH_PSEUDOS = frozenset({"is", "where", "matches", "-webkit-any", "-moz-any"})
GROUPING_AT_RULES = frozenset({"media", "supports", "layer", "container", "document"})
SCOPING_AT_RULES = frozenset({"scope"})
ROOT_ELEMENTS = frozenset({"html", "body"})
_COMBINATOR_LITERALS = frozenset({">", "+", "~"})


@dataclass
class ClassIndex:
    defined: set[str] = field(default_factory=set)
    scoped: set[str] = field(default_factory=set)
    context: set[str] = field(default_factory=set)

    def finalize(self) -> "ClassIndex":
        self.scoped -= self.defined
        self.context -= self.defined
        return self


def _split_commas(tokens) -> list[list]:
    parts, current = [], []
    for token in tokens:
        if token.type == "literal" and token.value == ",":
            parts.append(current)
            current = []
        else:
            current.append(token)
    parts.append(current)
    return parts


def _is_combinator(token) -> bool:
    return token.type == "whitespace" or (token.type == "literal" and token.value in _COMBINATOR_LITERALS)


def _compounds(tokens) -> tuple[list[list], list[str]]:
    """The compounds of one complex selector and the combinator before each one after the first.

    A combinator is ``" "`` (descendant), ``">"``, ``"+"`` or ``"~"``.
    """
    compounds, combinators, current, pending = [], [], [], None
    for token in tokens:  # comments are already gone: every parse call passes skip_comments=True
        if _is_combinator(token):
            if current:
                compounds.append(current)
                current = []
            literal = token.value if token.type == "literal" else " "
            pending = literal if pending in (None, " ") else pending
            continue
        if not current and compounds:
            combinators.append(pending or " ")
        pending = None
        current.append(token)
    if current:
        compounds.append(current)
    return compounds, combinators


def _is_root_compound(compound) -> bool:
    if len(compound) == 1 and compound[0].type == "ident":
        return compound[0].lower_value in ROOT_ELEMENTS
    return (
        len(compound) == 2
        and compound[0].type == "literal"
        and compound[0].value == ":"
        and compound[1].type == "ident"
        and compound[1].lower_value == "root"
    )


def _mentions(tokens, into: set[str]) -> None:
    """Add every class in ``tokens`` (at any depth, attribute selectors aside) to ``into``."""
    previous = None
    for token in tokens:
        if token.type == "ident" and previous is not None and previous.type == "literal" and previous.value == ".":
            into.add(token.value)
        elif token.type == "function":
            _mentions(token.arguments, into)
        elif token.type == "() block":
            _mentions(token.content, into)
        previous = token


def _is_class_token(token, previous) -> bool:
    return token.type == "ident" and previous is not None and previous.type == "literal" and previous.value == "."


def _shares_subject(compound) -> bool:
    """True when the compound needs more than one class: ``.a.b``, ``.a:is(.b)``, ``:is(.a):is(.b)``."""
    top_level, pass_throughs, previous = 0, 0, None
    for token in compound:
        if _is_class_token(token, previous):
            top_level += 1
        elif token.type == "function" and token.lower_name in PASS_THROUGH_PSEUDOS:
            mentioned: set[str] = set()
            _mentions(token.arguments, mentioned)
            pass_throughs += bool(mentioned)
        previous = token
    return top_level + pass_throughs > 1


def _analyse_compound(compound, *, role: str, index: ClassIndex) -> None:
    """``role`` is ``subject`` (no context, not nested), ``scoped`` or ``context``."""
    if role == "subject" and _shares_subject(compound):
        role = "scoped"
    classes, previous = [], None
    for token in compound:
        if _is_class_token(token, previous):
            classes.append(token.value)
        elif token.type == "function" and token.lower_name in PASS_THROUGH_PSEUDOS:
            for argument in _split_commas(token.arguments):
                _analyse_selector(argument, scoped=role != "subject", index=index, as_context=role == "context")
        elif token.type == "function":
            _mentions(token.arguments, index.scoped)
        elif token.type == "() block":
            _mentions(token.content, index.scoped)
        previous = token
    if role == "context":
        index.context.update(classes)
    elif role == "subject" and classes:
        index.defined.update(classes)
    else:
        index.scoped.update(classes)


def _analyse_selector(tokens, *, scoped: bool, index: ClassIndex, as_context: bool = False) -> None:
    compounds, combinators = _compounds(tokens)
    # ``html .x`` / ``body .x`` / ``:root .x`` match every .x; ``body > .x`` does not.
    while len(compounds) > 1 and combinators[0] == " " and _is_root_compound(compounds[0]):
        compounds.pop(0)
        combinators.pop(0)
    if not compounds:
        return
    *context, subject = compounds
    for compound in context:
        _analyse_compound(compound, role="context", index=index)
    if as_context:
        role = "context"
    elif scoped or context:
        role = "scoped"
    else:
        role = "subject"
    _analyse_compound(subject, role=role, index=index)


def _child_rules(content) -> list:
    return [
        item
        for item in tinycss2.parse_blocks_contents(content, skip_comments=True, skip_whitespace=True)
        if item.type in ("qualified-rule", "at-rule")
    ]


def _analyse_rules(rules, *, scoped: bool, index: ClassIndex) -> None:
    for rule in rules:
        if rule.type == "qualified-rule":
            for selector in _split_commas(rule.prelude):
                _analyse_selector(selector, scoped=scoped, index=index)
            _analyse_rules(_child_rules(rule.content), scoped=True, index=index)
        elif rule.type == "at-rule" and rule.content is not None:
            keyword = rule.lower_at_keyword
            if keyword in GROUPING_AT_RULES or keyword in SCOPING_AT_RULES:
                inner_scoped = scoped or keyword in SCOPING_AT_RULES
                _analyse_rules(_child_rules(rule.content), scoped=inner_scoped, index=index)


def css_class_index(css) -> ClassIndex:
    """The defined / scoped / context class names of a stylesheet."""
    rules = tinycss2.parse_stylesheet(css or "", skip_comments=True, skip_whitespace=True)
    index = ClassIndex()
    _analyse_rules(rules, scoped=False, index=index)
    return index.finalize()
