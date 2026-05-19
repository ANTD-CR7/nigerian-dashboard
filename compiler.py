# ================================
#   Taoheed Abdulmananan Olaosebikan 22/10267
#   Handles: + - * /  and ( )
#   3 Phases: Lexer, Parser, Evaluator
# ================================


# ─────────────────────
# PHASE 1: LEXER
# Break the input into tokens (small pieces)
# ─────────────────────

def lexer(text):
    tokens = []
    i = 0

    while i < len(text):
        ch = text[i]

        # skip spaces
        if ch == " ":
            i += 1
            continue

        # if it's a digit, grab the full number
        if ch.isdigit():
            num = ""
            while i < len(text) and text[i].isdigit():
                num += text[i]
                i += 1
            tokens.append(("NUMBER", int(num)))
            continue

        # if it's an operator or bracket
        if ch == "+":   tokens.append(("PLUS",     "+"))
        elif ch == "-": tokens.append(("MINUS",    "-"))
        elif ch == "*": tokens.append(("MULTIPLY", "*"))
        elif ch == "/": tokens.append(("DIVIDE",   "/"))
        elif ch == "(": tokens.append(("LPAREN",   "("))
        elif ch == ")": tokens.append(("RPAREN",   ")"))
        else:
            print(f"  Unknown character: {ch}")

        i += 1

    return tokens


# ─────────────────────
# PHASE 2: PARSER
# Build a parse tree from the tokens
# Respects PEMDAS: * and / before + and -
# ─────────────────────

tokens = []
pos    = 0

def current():
    return tokens[pos] if pos < len(tokens) else ("EOF", None)

def eat():
    global pos
    tok = tokens[pos]
    pos += 1
    return tok

def factor():
    tok = eat()
    if tok[0] == "NUMBER":
        return ("NUM", tok[1])
    if tok[0] == "LPAREN":
        node = expr()
        eat()   # consume RPAREN
        return node

def term():
    node = factor()
    while current()[0] in ("MULTIPLY", "DIVIDE"):
        op = eat()
        right = factor()
        node = (op[1], node, right)
    return node

def expr():
    node = term()
    while current()[0] in ("PLUS", "MINUS"):
        op = eat()
        right = term()
        node = (op[1], node, right)
    return node


# ─────────────────────
# PHASE 3: EVALUATOR
# Walk the tree and calculate the result
# ─────────────────────

def evaluate(node):
    if node[0] == "NUM":
        return node[1]

    op    = node[0]
    left  = evaluate(node[1])
    right = evaluate(node[2])

    if op == "+": return left + right
    if op == "-": return left - right
    if op == "*": return left * right
    if op == "/": return left / right


# ─────────────────────
# PRINT HELPERS
# ─────────────────────

def print_tokens(token_list):
    print("\n--- TOKENS ---")
    for i, (type_, value) in enumerate(token_list):
        print(f"  {i+1}. {type_:10}  {value}")

def print_tree(node, prefix="", is_last=True):
    connector = "└── " if is_last else "├── "

    if node[0] == "NUM":
        print(prefix + connector + str(node[1]))
    else:
        print(prefix + connector + f"[{node[0]}]")
        extension = "    " if is_last else "│   "
        print_tree(node[1], prefix + extension, is_last=False)
        print_tree(node[2], prefix + extension, is_last=True)


# ─────────────────────
# MAIN – run everything
# ─────────────────────

print("Simple Arithmetic Compiler")
print("Type 'quit' to exit\n")

while True:
    text = input("Enter expression: ").strip()

    if text.lower() == "quit":
        print("Goodbye!")
        break

    if text == "":
        continue

    # Phase 1
    token_list = lexer(text)
    print_tokens(token_list)

    # Phase 2
    tokens = token_list
    pos    = 0
    tree   = expr()

    print("\n--- PARSE TREE ---")
    print_tree(tree)

    # Phase 3
    result = evaluate(tree)
    print(f"\n--- RESULT ---")
    print(f"  {text} = {result}\n")