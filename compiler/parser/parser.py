from compiler.token import TokenType
from compiler.parser.ast import *


class Parser:
    def __init__(self, tokens: list):
        self.tokens = tokens
        self.pos = 0
        self.current_token = tokens[0] if tokens else None

    def error(self, message: str):
        tok = self.current_token
        raise SyntaxError(f"{message} at line {tok.line}, column {tok.col}")

    def advance(self):
        self.pos += 1
        if self.pos < len(self.tokens):
            self.current_token = self.tokens[self.pos]
        return self.current_token

    def peek(self, offset: int = 0) -> TokenType:
        idx = self.pos + offset
        if idx < len(self.tokens):
            return self.tokens[idx].type
        return TokenType.EOF

    def check(self, type_: TokenType) -> bool:
        return self.current_token.type == type_

    def expect(self, type_: TokenType) -> object:
        if self.check(type_):
            value = self.current_token.value
            self.advance()
            return value
        self.error(f"Expected {type_.name}, got {self.current_token.type.name} ('{self.current_token.value}')")

    def skip_newlines(self):
        while self.check(TokenType.NEWLINE):
            self.advance()

    def expect_identifier_or_keyword(self) -> str:
        if self.check(TokenType.IDENTIFIER):
            return self.expect(TokenType.IDENTIFIER)
        elif self.check(TokenType.KEYWORD):
            return self.expect(TokenType.KEYWORD)
        self.error(f"Expected identifier or keyword, got {self.current_token.type.name}")

    def parse(self) -> Program:
        declarations = []
        self.skip_newlines()
        while not self.check(TokenType.EOF):
            decl = self.parse_declaration()
            if decl:
                declarations.append(decl)
            self.skip_newlines()
        return Program(declarations=declarations)

    # ---- Top-level declarations ----

    def parse_declaration(self) -> Node:
        if not self.check(TokenType.KEYWORD):
            self.error(f"Unexpected token '{self.current_token.value}'")
        kw = self.current_token.value
        if kw == "neuron":
            return self.parse_neuron()
        elif kw == "region":
            return self.parse_region()
        elif kw == "data":
            return self.parse_data()
        elif kw == "train":
            return self.parse_train()
        elif kw == "infer":
            return self.parse_infer()
        elif kw == "use":
            return self.parse_use()
        elif kw == "fn":
            return self.parse_fn()
        elif kw == "let":
            return self.parse_var_decl()
        self.error(f"Unexpected keyword '{kw}'")

    def parse_use(self) -> UseStmt:
        self.expect(TokenType.KEYWORD)
        path = self.expect(TokenType.STRING)
        return UseStmt(path=path)

    # ---- Functions ----

    def parse_fn(self) -> FuncDef:
        self.expect(TokenType.KEYWORD)
        name = self.expect(TokenType.IDENTIFIER)
        self.expect(TokenType.LPAREN)
        params = []
        while not self.check(TokenType.RPAREN) and not self.check(TokenType.EOF):
            p_name = self.expect(TokenType.IDENTIFIER)
            p_type = None
            if self.check(TokenType.COLON):
                self.advance()
                p_type = self.parse_type()
            params.append(VarDecl(name=p_name, type=p_type))
            if self.check(TokenType.COMMA):
                self.advance()
        self.expect(TokenType.RPAREN)
        return_type = None
        if self.check(TokenType.ARROW):
            self.advance()
            return_type = self.parse_type()
        body = self.parse_block()
        return FuncDef(name=name, params=params, return_type=return_type, body=body)

    # ---- Blocks ----

    def parse_block(self) -> Block:
        self.expect(TokenType.LBRACE)
        self.skip_newlines()
        stmts = []
        while not self.check(TokenType.RBRACE) and not self.check(TokenType.EOF):
            stmt = self.parse_statement()
            if stmt:
                stmts.append(stmt)
            self.skip_newlines()
        self.expect(TokenType.RBRACE)
        return Block(statements=stmts)

    def parse_statement(self) -> Node:
        if self.check(TokenType.KEYWORD):
            kw = self.current_token.value
            if kw == "if":
                return self.parse_if()
            elif kw == "for":
                return self.parse_for()
            elif kw == "while":
                return self.parse_while()
            elif kw == "return":
                return self.parse_return()
            elif kw == "let":
                return self.parse_var_decl()
            elif kw == "fn":
                return self.parse_fn()
            elif kw == "train":
                return self.parse_train()
            elif kw == "infer":
                return self.parse_infer()
        if self.check(TokenType.IDENTIFIER) or self.check(TokenType.KEYWORD):
            name = self.current_token.value
            if (self.peek(1) == TokenType.EQUALS or
                self.peek(1) == TokenType.COLON):
                if self.peek(1) == TokenType.COLON:
                    return self.parse_var_decl()
                target = self.expect_identifier_or_keyword()
                self.expect(TokenType.EQUALS)
                expr = self.parse_expression()
                return Assignment(target=target, value=expr)
            # могливо це тип + EQUALS для var decl
            return self.parse_expression()
        if self.check(TokenType.LBRACE):
            return self.parse_block()
        return self.parse_expression()

    # ---- Control flow ----

    def parse_if(self) -> IfStmt:
        self.expect(TokenType.KEYWORD)
        cond = self.parse_expression()
        then_b = self.parse_block()
        else_b = None
        if self.check(TokenType.KEYWORD) and self.current_token.value == "else":
            self.advance()
            if self.check(TokenType.KEYWORD) and self.current_token.value == "if":
                inner = self.parse_if()
                else_b = Block(statements=[inner])
            else:
                else_b = self.parse_block()
        return IfStmt(condition=cond, then_block=then_b, else_block=else_b)

    def parse_for(self) -> ForStmt:
        self.expect(TokenType.KEYWORD)
        var = self.expect(TokenType.IDENTIFIER)
        self.expect(TokenType.KEYWORD) if self.current_token.value == "in" else self.expect(TokenType.KEYWORD)
        start = self.parse_expression()
        self.expect(TokenType.DOTDOT)
        end = self.parse_expression()
        body = self.parse_block()
        return ForStmt(var=var, start=start, end=end, body=body)

    def parse_while(self) -> WhileStmt:
        self.expect(TokenType.KEYWORD)
        cond = self.parse_expression()
        body = self.parse_block()
        return WhileStmt(condition=cond, body=body)

    def parse_return(self) -> ReturnStmt:
        self.expect(TokenType.KEYWORD)
        if self.check(TokenType.RBRACE) or self.check(TokenType.NEWLINE):
            return ReturnStmt()
        value = self.parse_expression()
        return ReturnStmt(value=value)

    def parse_var_decl(self) -> VarDecl:
        is_let = self.check(TokenType.KEYWORD) and self.current_token.value == "let"
        if is_let:
            self.advance()
        name = self.expect(TokenType.IDENTIFIER)
        type_ref = None
        if self.check(TokenType.COLON):
            self.advance()
            type_ref = self.parse_type()
        value = None
        if self.check(TokenType.EQUALS):
            self.advance()
            value = self.parse_expression()
        return VarDecl(name=name, type=type_ref, value=value)

    # ---- Types ----

    def parse_type(self) -> Node:
        if self.check(TokenType.KEYWORD):
            kw = self.current_token.value
            if kw == "archive":
                self.advance()
                self.expect(TokenType.LBRACE)
                inner = self.parse_type()
                self.expect(TokenType.COMMA)
                levels = self.expect(TokenType.NUMBER)
                self.expect(TokenType.RBRACE)
                return ArchiveType(inner_type=inner, levels=levels)
            elif kw == "state":
                self.advance()
                self.expect(TokenType.LBRACKET)
                size = self.expect(TokenType.NUMBER)
                self.expect(TokenType.RBRACKET)
                return StateType(size=size)
            elif kw == "tensor":
                self.advance()
                self.expect(TokenType.LBRACKET)
                dims = [self.expect(TokenType.NUMBER)]
                while self.check(TokenType.COMMA):
                    self.advance()
                    dims.append(self.expect(TokenType.NUMBER))
                self.expect(TokenType.RBRACKET)
                return TypeRef(name="tensor", params=[Literal(v) for v in dims])
            elif kw == "list":
                self.advance()
                inner = None
                if self.check(TokenType.LBRACKET):
                    self.advance()
                    inner = self.parse_type()
                    self.expect(TokenType.RBRACKET)
                return TypeRef(name="list", params=[inner] if inner else [])
            else:
                self.advance()
                return TypeRef(name=kw)
        elif self.check(TokenType.IDENTIFIER):
            name = self.current_token.value
            self.advance()
            return TypeRef(name=name)
        self.error(f"Expected type, got '{self.current_token.value}'")

    # ---- Neuron ----

    def parse_neuron(self) -> NeuronDef:
        self.expect(TokenType.KEYWORD)
        name = self.expect_identifier_or_keyword()
        self.expect(TokenType.LBRACE)
        self.skip_newlines()
        nucleus = None
        membrane = None
        dynamics = None
        while not self.check(TokenType.RBRACE) and not self.check(TokenType.EOF):
            kw = self.current_token.value
            if kw == "nucleus":
                self.advance()
                self.expect(TokenType.COLON)
                nucleus = self.parse_type()
                self.skip_newlines()
            elif kw == "membrane":
                self.advance()
                self.expect(TokenType.LBRACE)
                self.skip_newlines()
                pot = thr = ref = None
                while not self.check(TokenType.RBRACE) and not self.check(TokenType.EOF):
                    key = self.expect_identifier_or_keyword()
                    self.expect(TokenType.COLON)
                    val = self.parse_literal()
                    if key == "potential":
                        pot = val
                    elif key == "threshold":
                        thr = val
                    elif key == "refractory":
                        ref = val
                    self.skip_newlines()
                self.expect(TokenType.RBRACE)
                membrane = MembraneDef(potential=pot, threshold=thr, refractory=ref)
                self.skip_newlines()
            elif kw == "dynamics":
                self.advance()
                self.expect(TokenType.LBRACE)
                self.skip_newlines()
                stmts = []
                while not self.check(TokenType.RBRACE) and not self.check(TokenType.EOF):
                    stmt = self.parse_statement()
                    if stmt:
                        stmts.append(stmt)
                    self.skip_newlines()
                self.expect(TokenType.RBRACE)
                dynamics = DynamicsDef(statements=stmts)
                self.skip_newlines()
            else:
                self.error(f"Unknown neuron field '{kw}'")
        self.expect(TokenType.RBRACE)
        return NeuronDef(name=name, nucleus=nucleus, membrane=membrane, dynamics=dynamics)

    # ---- Expressions ----

    def parse_literal(self) -> Node:
        if self.check(TokenType.NUMBER):
            val = self.current_token.value
            self.advance()
            return Literal(value=val)
        elif self.check(TokenType.FLOAT):
            val = self.current_token.value
            self.advance()
            return Literal(value=val)
        elif self.check(TokenType.STRING):
            val = self.current_token.value
            self.advance()
            return Literal(value=val)
        elif self.check(TokenType.IDENTIFIER):
            name = self.current_token.value
            self.advance()
            if self.check(TokenType.LPAREN):
                return self.parse_call(name)
            return Identifier(name=name)
        elif self.check(TokenType.KEYWORD):
            val = self.current_token.value
            self.advance()
            if val in ("true", "false"):
                return Literal(value=val == "true")
            if self.check(TokenType.LPAREN):
                return self.parse_call(val)
            return Identifier(name=val)
        elif self.check(TokenType.LPAREN):
            self.advance()
            expr = self.parse_expression()
            self.expect(TokenType.RPAREN)
            return expr
        elif self.check(TokenType.BANG):
            self.advance()
            operand = self.parse_literal()
            return UnaryOp(op="!", operand=operand)
        self.error(f"Expected literal, got '{self.current_token.value}'")

    def parse_call(self, name: str) -> Node:
        self.expect(TokenType.LPAREN)
        args = []
        while not self.check(TokenType.RPAREN) and not self.check(TokenType.EOF):
            args.append(self.parse_expression())
            if self.check(TokenType.COMMA):
                self.advance()
        self.expect(TokenType.RPAREN)
        return Call(name=name, args=args)

    def parse_expression(self) -> Node:
        left = self._parse_or()
        while self.check(TokenType.LESS) or self.check(TokenType.GREATER) or \
              self.check(TokenType.LE) or self.check(TokenType.GE) or \
              self.check(TokenType.EQEQ) or self.check(TokenType.NE):
            op = self.current_token.value
            self.advance()
            right = self._parse_or()
            left = BinaryOp(left=left, op=op, right=right)
        return left

    def _parse_or(self) -> Node:
        left = self._parse_and()
        while self.check(TokenType.PIPEPIPE) or \
              (self.check(TokenType.KEYWORD) and self.current_token.value == "or"):
            self.advance()
            right = self._parse_and()
            left = BinaryOp(left=left, op="||", right=right)
        return left

    def _parse_and(self) -> Node:
        left = self._parse_additive()
        while self.check(TokenType.ANDAND) or \
              (self.check(TokenType.KEYWORD) and self.current_token.value == "and"):
            self.advance()
            right = self._parse_additive()
            left = BinaryOp(left=left, op="&&", right=right)
        return left

    def _parse_additive(self) -> Node:
        left = self.parse_literal()
        while self.check(TokenType.PLUS) or self.check(TokenType.MINUS) or \
              self.check(TokenType.STAR) or self.check(TokenType.SLASH) or \
              self.check(TokenType.PERCENT):
            op = self.current_token.value
            self.advance()
            right = self.parse_literal()
            left = BinaryOp(left=left, op=op, right=right)
        return left

    # ---- Region, connection, data, train, infer ----

    def parse_region(self) -> RegionDef:
        self.expect(TokenType.KEYWORD)
        name = self.expect_identifier_or_keyword()
        self.expect(TokenType.LBRACE)
        self.skip_newlines()
        neuron_type = ""
        count = 0
        connections = []
        while not self.check(TokenType.RBRACE) and not self.check(TokenType.EOF):
            if self.check(TokenType.KEYWORD) and self.current_token.value == "connect":
                conn = self.parse_connection()
                connections.append(conn)
            elif self.check(TokenType.IDENTIFIER) or self.check(TokenType.KEYWORD):
                field = self.expect_identifier_or_keyword()
                if field == "neurons":
                    self.expect(TokenType.COLON)
                    nt = self.parse_type()
                    self.expect(TokenType.LBRACKET)
                    count = self.expect(TokenType.NUMBER)
                    self.expect(TokenType.RBRACKET)
                    neuron_type = nt.name if hasattr(nt, "name") else str(nt)
            self.skip_newlines()
        self.expect(TokenType.RBRACE)
        return RegionDef(name=name, neuron_type=neuron_type, count=count, connections=connections)

    def parse_connection(self) -> ConnectionDef:
        self.expect(TokenType.KEYWORD)
        src = self.expect_identifier_or_keyword()
        self.expect(TokenType.ARROW)
        tgt = self.expect_identifier_or_keyword()
        self.expect(TokenType.COLON)
        pattern = ""
        sparsity = None
        if self.check(TokenType.IDENTIFIER):
            pattern = self.expect(TokenType.IDENTIFIER)
        elif self.check(TokenType.KEYWORD):
            pattern = self.expect(TokenType.KEYWORD)
        if self.check(TokenType.LPAREN):
            self.advance()
            sparsity = self.parse_literal()
            self.expect(TokenType.RPAREN)
        plasticity = ""
        branching = None
        if self.check(TokenType.LBRACE):
            self.advance()
            self.skip_newlines()
            while not self.check(TokenType.RBRACE) and not self.check(TokenType.EOF):
                key = self.current_token.value
                if self.check(TokenType.IDENTIFIER):
                    key = self.expect(TokenType.IDENTIFIER)
                elif self.check(TokenType.KEYWORD):
                    key = self.expect(TokenType.KEYWORD)
                self.expect(TokenType.COLON)
                if key == "plasticity":
                    plasticity = self.expect(TokenType.IDENTIFIER) if self.check(TokenType.IDENTIFIER) else self.expect(TokenType.KEYWORD)
                elif key == "branching":
                    branching = self.parse_literal()
                elif key == "sparsity":
                    sparsity = self.parse_literal()
                else:
                    self.parse_literal()
                self.skip_newlines()
            self.expect(TokenType.RBRACE)
        return ConnectionDef(source=src, target=tgt, pattern=pattern, sparsity=sparsity, plasticity=plasticity, branching=branching)

    def parse_data(self) -> DataDef:
        self.expect(TokenType.KEYWORD)
        name = self.expect_identifier_or_keyword()
        self.expect(TokenType.LBRACE)
        self.skip_newlines()
        source = ""
        shape = []
        while not self.check(TokenType.RBRACE) and not self.check(TokenType.EOF):
            key = self.expect_identifier_or_keyword()
            self.expect(TokenType.COLON)
            if key == "source":
                source = self.expect(TokenType.STRING)
            elif key == "shape":
                self.expect(TokenType.LBRACKET)
                shape.append(self.expect(TokenType.NUMBER))
                while self.check(TokenType.COMMA):
                    self.advance()
                    shape.append(self.expect(TokenType.NUMBER))
                self.expect(TokenType.RBRACKET)
            self.skip_newlines()
        self.expect(TokenType.RBRACE)
        return DataDef(name=name, source=source, shape=shape)

    def parse_train(self) -> TrainStmt:
        self.expect(TokenType.KEYWORD)
        region = self.expect_identifier_or_keyword()
        self.expect(TokenType.KEYWORD)
        dataset = self.expect_identifier_or_keyword()
        self.expect(TokenType.LBRACE)
        self.skip_newlines()
        params = []
        while not self.check(TokenType.RBRACE) and not self.check(TokenType.EOF):
            key = self.current_token.value
            if self.check(TokenType.IDENTIFIER):
                key = self.expect(TokenType.IDENTIFIER)
            elif self.check(TokenType.KEYWORD):
                key = self.expect(TokenType.KEYWORD)
            self.expect(TokenType.COLON)
            val = self.parse_literal()
            params.append(ParamAssign(key=key, value=val))
            self.skip_newlines()
        self.expect(TokenType.RBRACE)
        return TrainStmt(region=region, dataset=dataset, params=params)

    def parse_infer(self) -> InferStmt:
        self.expect(TokenType.KEYWORD)
        region = self.expect_identifier_or_keyword()
        self.expect(TokenType.KEYWORD)
        input_ = self.expect_identifier_or_keyword()
        self.expect(TokenType.LBRACE)
        self.skip_newlines()
        output = ""
        while not self.check(TokenType.RBRACE) and not self.check(TokenType.EOF):
            key = self.expect_identifier_or_keyword()
            self.expect(TokenType.ARROW)
            output = self.expect_identifier_or_keyword()
            self.skip_newlines()
        self.expect(TokenType.RBRACE)
        return InferStmt(region=region, input=input_, output=output)
