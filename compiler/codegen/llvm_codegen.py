"""Generate LLVM IR from Million MIR (requires llvmlite)."""

from __future__ import annotations

from compiler.ir.million_ir import MIRFunction, MIRNeuron


def llvmlite_available() -> bool:
    try:
        import llvmlite  # noqa: F401
        return True
    except ImportError:
        return False


class LLVMCodeGen:
    """Emit verifiable LLVM IR for archive ops, neurons, and main."""

    def __init__(self, mir_module):
        self.module = mir_module
        self._ir = None
        self._llvm = None

    def _ensure_llvm(self):
        if self._llvm is not None:
            return
        import llvmlite.binding as llvm
        import llvmlite.ir as ir

        self._llvm = llvm
        self._ir = ir

    def generate(self) -> str:
        self._ensure_llvm()
        ir = self._ir
        mod = ir.Module(name="million_module")
        f32 = ir.FloatType()
        i32 = ir.IntType(32)
        void = ir.VoidType()
        fptr = f32.as_pointer()

        self._declare_externs(mod, ir, f32, i32)
        self._emit_archive_unfold(mod, ir, f32, i32, void, fptr)
        self._emit_archive_compress(mod, ir, f32, i32, void, fptr)
        self._emit_archive_unfold_grad(mod, ir, f32, i32, void, fptr)
        self._emit_archive_compress_grad(mod, ir, f32, i32, void, fptr)
        for neuron in self.module.neurons:
            self._emit_process(mod, ir, neuron, f32, i32, fptr)
            self._emit_init(mod, ir, neuron, f32, i32, void)
        for func in self.module.functions:
            self._emit_mir_function(mod, ir, f32, i32, void, func)
        self._emit_main(mod, ir, i32, void)
        llvm_ir = str(mod)
        self._verify(llvm_ir)
        return llvm_ir

    def _declare_externs(self, mod, ir, f32, i32):
        for name, fty in [
            ("sinf", ir.FunctionType(f32, [f32])),
            ("tanhf", ir.FunctionType(f32, [f32])),
        ]:
            if name not in mod.global_values:
                ir.Function(mod, fty, name=name)

    def _verify(self, llvm_ir: str) -> None:
        try:
            self._llvm.parse_assembly(llvm_ir).verify()
        except Exception as exc:
            raise RuntimeError(f"LLVM verify failed: {exc}") from exc

    def _emit_archive_unfold(self, mod, ir, f32, i32, void, fptr):
        fn = ir.Function(
            mod,
            ir.FunctionType(void, [fptr, i32, fptr, i32, i32]),
            name="archive_unfold",
        )
        in_p, in_sz, out_p, out_sz, level = fn.args
        entry = fn.append_basic_block("entry")
        loop_i = fn.append_basic_block("loop_i")
        loop_body = fn.append_basic_block("loop_body")
        loop_j = fn.append_basic_block("loop_j")
        j_body = fn.append_basic_block("j_body")
        after_j = fn.append_basic_block("after_j")
        done = fn.append_basic_block("done")

        b = ir.IRBuilder(entry)
        i_phi = b.alloca(i32, name="i")
        j_phi = b.alloca(i32, name="j")
        sum_a = b.alloca(f32, name="sum")
        b.store(ir.Constant(i32, 0), i_phi)
        b.branch(loop_i)

        b.position_at_end(loop_i)
        i_v = b.load(i_phi)
        b.cbranch(b.icmp_signed("<", i_v, out_sz), loop_body, done)

        b.position_at_end(loop_body)
        b.store(ir.Constant(f32, 0.0), sum_a)
        b.store(ir.Constant(i32, 0), j_phi)
        b.branch(loop_j)

        b.position_at_end(loop_j)
        j_v = b.load(j_phi)
        b.cbranch(b.icmp_signed("<", j_v, in_sz), j_body, after_j)

        b.position_at_end(j_body)
        val = b.load(b.gep(in_p, [j_v]))
        ij = b.add(b.mul(i_v, j_v), level)
        sarg = b.call(mod.get_global("sinf"), [b.sitofp(ij, f32)])
        b.store(b.fadd(b.load(sum_a), b.fmul(val, sarg)), sum_a)
        b.store(b.add(j_v, ir.Constant(i32, 1)), j_phi)
        b.branch(loop_j)

        b.position_at_end(after_j)
        norm = b.fdiv(b.load(sum_a), b.sitofp(in_sz, f32))
        out_v = b.call(mod.get_global("tanhf"), [norm])
        b.store(out_v, b.gep(out_p, [i_v]))
        b.store(b.add(i_v, ir.Constant(i32, 1)), i_phi)
        b.branch(loop_i)

        b.position_at_end(done)
        b.ret_void()

    def _emit_archive_compress(self, mod, ir, f32, i32, void, fptr):
        fn = ir.Function(
            mod,
            ir.FunctionType(void, [fptr, i32, fptr, i32]),
            name="archive_compress",
        )
        in_p, in_sz, out_p, out_sz = fn.args
        entry = fn.append_basic_block("entry")
        li = fn.append_basic_block("li")
        body = fn.append_basic_block("body")
        lj = fn.append_basic_block("lj")
        jb = fn.append_basic_block("jb")
        sk = fn.append_basic_block("sk")
        lje = fn.append_basic_block("lje")
        ld = fn.append_basic_block("ld")

        b = ir.IRBuilder(entry)
        group = b.alloca(i32)
        g = b.sdiv(in_sz, out_sz)
        b.store(
            b.select(
                b.icmp_signed("<", g, ir.Constant(i32, 1)),
                ir.Constant(i32, 1),
                g,
            ),
            group,
        )
        i_a = b.alloca(i32)
        b.store(ir.Constant(i32, 0), i_a)
        b.branch(li)

        b.position_at_end(li)
        i_v = b.load(i_a)
        b.cbranch(b.icmp_signed("<", i_v, out_sz), body, ld)

        b.position_at_end(body)
        g_v = b.load(group)
        start = b.mul(i_v, g_v)
        sum_a = b.alloca(f32)
        b.store(ir.Constant(f32, 0.0), sum_a)
        j_a = b.alloca(i32)
        b.store(ir.Constant(i32, 0), j_a)
        b.branch(lj)

        b.position_at_end(lj)
        j_v = b.load(j_a)
        b.cbranch(b.icmp_signed("<", j_v, g_v), jb, lje)

        doa = fn.append_basic_block("doa")
        b.position_at_end(jb)
        pos = b.add(start, j_v)
        b.cbranch(b.icmp_signed("<", pos, in_sz), doa, sk)
        b.position_at_end(doa)
        v = b.load(b.gep(in_p, [pos]))
        b.store(b.fadd(b.load(sum_a), v), sum_a)
        b.branch(sk)

        b.position_at_end(sk)
        b.store(b.add(j_v, ir.Constant(i32, 1)), j_a)
        b.branch(lj)

        b.position_at_end(lje)
        gv = b.sitofp(b.load(group), f32)
        out_v = b.call(mod.get_global("tanhf"), [b.fdiv(b.load(sum_a), gv)])
        b.store(out_v, b.gep(out_p, [i_v]))
        b.store(b.add(i_v, ir.Constant(i32, 1)), i_a)
        b.branch(li)

        b.position_at_end(ld)
        b.ret_void()

    def _emit_archive_unfold_grad(self, mod, ir, f32, i32, void, fptr):
        """Mirror C archive_unfold_grad."""
        fn = ir.Function(
            mod,
            ir.FunctionType(
                void,
                [fptr, i32, fptr, i32, i32, fptr, fptr],
            ),
            name="archive_unfold_grad",
        )
        in_p, in_sz, _out_p, out_sz, level, grad_out, grad_in = fn.args
        sinf = mod.get_global("sinf")
        tanhf = mod.get_global("tanhf")

        entry = fn.append_basic_block("entry")
        zj = fn.append_basic_block("zj")
        zj_body = fn.append_basic_block("zj_body")
        zj_done = fn.append_basic_block("zj_done")
        loop_i = fn.append_basic_block("loop_i")
        body_i = fn.append_basic_block("body_i")
        fwd_j = fn.append_basic_block("fwd_j")
        fwd_body = fn.append_basic_block("fwd_body")
        fwd_j_done = fn.append_basic_block("fwd_j_done")
        grad_j = fn.append_basic_block("grad_j")
        grad_body = fn.append_basic_block("grad_body")
        grad_j_done = fn.append_basic_block("grad_j_done")
        done = fn.append_basic_block("done")

        b = ir.IRBuilder(entry)
        j_a = b.alloca(i32, name="j")
        i_a = b.alloca(i32, name="i")
        sum_a = b.alloca(f32, name="sum")
        dtanh_a = b.alloca(f32, name="dtanh")

        b.store(ir.Constant(i32, 0), j_a)
        b.branch(zj)
        b.position_at_end(zj)
        j_v = b.load(j_a)
        b.cbranch(b.icmp_signed("<", j_v, in_sz), zj_body, zj_done)
        b.position_at_end(zj_body)
        b.store(ir.Constant(f32, 0.0), b.gep(grad_in, [j_v]))
        b.store(b.add(j_v, ir.Constant(i32, 1)), j_a)
        b.branch(zj)

        b.position_at_end(zj_done)
        b.store(ir.Constant(i32, 0), i_a)
        b.branch(loop_i)

        b.position_at_end(loop_i)
        i_v = b.load(i_a)
        b.cbranch(b.icmp_signed("<", i_v, out_sz), body_i, done)

        b.position_at_end(body_i)
        b.store(ir.Constant(f32, 0.0), sum_a)
        b.store(ir.Constant(i32, 0), j_a)
        b.branch(fwd_j)

        b.position_at_end(fwd_j)
        j_v = b.load(j_a)
        b.cbranch(b.icmp_signed("<", j_v, in_sz), fwd_body, fwd_j_done)
        b.position_at_end(fwd_body)
        val = b.load(b.gep(in_p, [j_v]))
        ij = b.add(b.mul(i_v, j_v), level)
        sarg = b.call(sinf, [b.sitofp(ij, f32)])
        b.store(b.fadd(b.load(sum_a), b.fmul(val, sarg)), sum_a)
        b.store(b.add(j_v, ir.Constant(i32, 1)), j_a)
        b.branch(fwd_j)

        b.position_at_end(fwd_j_done)
        act = b.call(tanhf, [b.fdiv(b.load(sum_a), b.sitofp(in_sz, f32))])
        b.store(b.fsub(ir.Constant(f32, 1.0), b.fmul(act, act)), dtanh_a)

        b.store(ir.Constant(i32, 0), j_a)
        b.branch(grad_j)

        b.position_at_end(grad_j)
        j_v = b.load(j_a)
        b.cbranch(b.icmp_signed("<", j_v, in_sz), grad_body, grad_j_done)
        b.position_at_end(grad_body)
        gout = b.load(b.gep(grad_out, [i_v]))
        ij = b.add(b.mul(i_v, j_v), level)
        sarg = b.call(sinf, [b.sitofp(ij, f32)])
        contrib = b.fmul(
            gout,
            b.fmul(b.load(dtanh_a), b.fdiv(sarg, b.sitofp(in_sz, f32))),
        )
        gptr = b.gep(grad_in, [j_v])
        b.store(b.fadd(b.load(gptr), contrib), gptr)
        b.store(b.add(j_v, ir.Constant(i32, 1)), j_a)
        b.branch(grad_j)

        b.position_at_end(grad_j_done)
        b.store(b.add(i_v, ir.Constant(i32, 1)), i_a)
        b.branch(loop_i)

        b.position_at_end(done)
        b.ret_void()

    def _emit_archive_compress_grad(self, mod, ir, f32, i32, void, fptr):
        """Mirror C archive_compress_grad."""
        fn = ir.Function(
            mod,
            ir.FunctionType(void, [fptr, i32, fptr, i32, fptr, fptr]),
            name="archive_compress_grad",
        )
        in_p, in_sz, _out_p, out_sz, grad_out, grad_in = fn.args
        tanhf = mod.get_global("tanhf")

        entry = fn.append_basic_block("entry")
        zj = fn.append_basic_block("zj")
        zj_body = fn.append_basic_block("zj_body")
        zj_done = fn.append_basic_block("zj_done")
        loop_i = fn.append_basic_block("loop_i")
        body_i = fn.append_basic_block("body_i")
        fwd_j = fn.append_basic_block("fwd_j")
        fwd_body = fn.append_basic_block("fwd_body")
        fwd_add = fn.append_basic_block("fwd_add")
        fwd_skip = fn.append_basic_block("fwd_skip")
        fwd_j_done = fn.append_basic_block("fwd_j_done")
        grad_j = fn.append_basic_block("grad_j")
        grad_body = fn.append_basic_block("grad_body")
        grad_add = fn.append_basic_block("grad_add")
        grad_skip = fn.append_basic_block("grad_skip")
        grad_j_done = fn.append_basic_block("grad_j_done")
        done = fn.append_basic_block("done")

        b = ir.IRBuilder(entry)
        group_a = b.alloca(i32, name="group")
        g = b.sdiv(in_sz, out_sz)
        b.store(
            b.select(
                b.icmp_signed("<", g, ir.Constant(i32, 1)),
                ir.Constant(i32, 1),
                g,
            ),
            group_a,
        )
        j_a = b.alloca(i32, name="j")
        i_a = b.alloca(i32, name="i")
        sum_a = b.alloca(f32, name="sum")
        dtanh_a = b.alloca(f32, name="dtanh")

        b.store(ir.Constant(i32, 0), j_a)
        b.branch(zj)
        b.position_at_end(zj)
        j_v = b.load(j_a)
        b.cbranch(b.icmp_signed("<", j_v, in_sz), zj_body, zj_done)
        b.position_at_end(zj_body)
        b.store(ir.Constant(f32, 0.0), b.gep(grad_in, [j_v]))
        b.store(b.add(j_v, ir.Constant(i32, 1)), j_a)
        b.branch(zj)

        b.position_at_end(zj_done)
        b.store(ir.Constant(i32, 0), i_a)
        b.branch(loop_i)

        b.position_at_end(loop_i)
        i_v = b.load(i_a)
        b.cbranch(b.icmp_signed("<", i_v, out_sz), body_i, done)

        b.position_at_end(body_i)
        g_v = b.load(group_a)
        start = b.mul(i_v, g_v)
        b.store(ir.Constant(f32, 0.0), sum_a)
        b.store(ir.Constant(i32, 0), j_a)
        b.branch(fwd_j)

        b.position_at_end(fwd_j)
        j_v = b.load(j_a)
        b.cbranch(b.icmp_signed("<", j_v, g_v), fwd_body, fwd_j_done)
        b.position_at_end(fwd_body)
        pos = b.add(start, j_v)
        b.cbranch(b.icmp_signed("<", pos, in_sz), fwd_add, fwd_skip)
        b.position_at_end(fwd_add)
        v = b.load(b.gep(in_p, [pos]))
        b.store(b.fadd(b.load(sum_a), v), sum_a)
        b.branch(fwd_skip)
        b.position_at_end(fwd_skip)
        b.store(b.add(j_v, ir.Constant(i32, 1)), j_a)
        b.branch(fwd_j)

        b.position_at_end(fwd_j_done)
        gv = b.sitofp(b.load(group_a), f32)
        act = b.call(tanhf, [b.fdiv(b.load(sum_a), gv)])
        b.store(b.fsub(ir.Constant(f32, 1.0), b.fmul(act, act)), dtanh_a)

        b.store(ir.Constant(i32, 0), j_a)
        b.branch(grad_j)

        b.position_at_end(grad_j)
        j_v = b.load(j_a)
        b.cbranch(b.icmp_signed("<", j_v, g_v), grad_body, grad_j_done)
        b.position_at_end(grad_body)
        pos = b.add(start, j_v)
        b.cbranch(b.icmp_signed("<", pos, in_sz), grad_add, grad_skip)
        b.position_at_end(grad_add)
        gout = b.load(b.gep(grad_out, [i_v]))
        contrib = b.fdiv(b.fmul(gout, b.load(dtanh_a)), gv)
        gptr = b.gep(grad_in, [pos])
        b.store(b.fadd(b.load(gptr), contrib), gptr)
        b.branch(grad_skip)
        b.position_at_end(grad_skip)
        b.store(b.add(j_v, ir.Constant(i32, 1)), j_a)
        b.branch(grad_j)

        b.position_at_end(grad_j_done)
        b.store(b.add(i_v, ir.Constant(i32, 1)), i_a)
        b.branch(loop_i)

        b.position_at_end(done)
        b.ret_void()

    def _neuron_ty(self, ir, neuron: MIRNeuron):
        f32 = ir.FloatType()
        return ir.LiteralStructType(
            [
                ir.ArrayType(f32, neuron.nucleus_size),
                ir.LiteralStructType([f32, f32, f32, ir.IntType(32)]),
                f32,
            ]
        )

    def _emit_init(self, mod, ir, neuron: MIRNeuron, f32, i32, void):
        ty = self._neuron_ty(ir, neuron)
        fn = ir.Function(mod, ir.FunctionType(void, [ty.as_pointer()]), name=f"init_{neuron.name}")
        b = ir.IRBuilder(fn.append_basic_block("entry"))
        n = fn.args[0]
        nuc = b.gep(n, [ir.Constant(i32, 0), ir.Constant(i32, 0)])
        for idx in range(neuron.nucleus_size):
            b.store(
                ir.Constant(f32, 0.0),
                b.gep(nuc, [ir.Constant(i32, 0), ir.Constant(i32, idx)]),
            )
        mem = b.gep(n, [ir.Constant(i32, 0), ir.Constant(i32, 1)])
        b.store(ir.Constant(f32, 0.0), b.gep(mem, [ir.Constant(i32, 0), ir.Constant(i32, 0)]))
        b.store(ir.Constant(f32, 1.0), b.gep(mem, [ir.Constant(i32, 0), ir.Constant(i32, 1)]))
        b.store(
            ir.Constant(f32, float(neuron.refractory_period)),
            b.gep(mem, [ir.Constant(i32, 0), ir.Constant(i32, 2)]),
        )
        b.store(ir.Constant(i32, 0), b.gep(mem, [ir.Constant(i32, 0), ir.Constant(i32, 3)]))
        b.store(ir.Constant(f32, 0.0), b.gep(n, [ir.Constant(i32, 0), ir.Constant(i32, 2)]))
        b.ret_void()

    def _emit_process(self, mod, ir, neuron: MIRNeuron, f32, i32, fptr):
        ty = self._neuron_ty(ir, neuron)
        fn = ir.Function(
            mod,
            ir.FunctionType(i32, [ty.as_pointer(), fptr, i32]),
            name=f"process_{neuron.name}",
        )
        n, inp, _sz = fn.args
        entry = fn.append_basic_block("entry")
        ref_bb = fn.append_basic_block("ref")
        cont = fn.append_basic_block("cont")
        fire = fn.append_basic_block("fire")
        nofire = fn.append_basic_block("nofire")
        end = fn.append_basic_block("end")

        b = ir.IRBuilder(entry)
        mem = b.gep(n, [ir.Constant(i32, 0), ir.Constant(i32, 1)])
        refr = b.gep(mem, [ir.Constant(i32, 0), ir.Constant(i32, 3)])
        b.cbranch(b.icmp_signed(">", b.load(refr), ir.Constant(i32, 0)), ref_bb, cont)

        b.position_at_end(ref_bb)
        b.store(ir.Constant(f32, 0.0), b.gep(n, [ir.Constant(i32, 0), ir.Constant(i32, 2)]))
        b.ret(ir.Constant(i32, 0))

        b.position_at_end(cont)
        pot_p = b.gep(mem, [ir.Constant(i32, 0), ir.Constant(i32, 0)])
        thr_p = b.gep(mem, [ir.Constant(i32, 0), ir.Constant(i32, 1)])
        out_p = b.gep(n, [ir.Constant(i32, 0), ir.Constant(i32, 2)])
        pot = b.load(pot_p)
        new_pot = b.fadd(pot, b.load(inp))
        b.store(new_pot, pot_p)
        b.cbranch(b.fcmp_ordered(">=", new_pot, b.load(thr_p)), fire, nofire)

        b.position_at_end(fire)
        b.store(new_pot, out_p)
        b.store(ir.Constant(f32, 0.0), pot_p)
        ref_f = b.gep(mem, [ir.Constant(i32, 0), ir.Constant(i32, 2)])
        b.store(b.fptosi(b.load(ref_f), i32), refr)
        b.branch(end)

        b.position_at_end(nofire)
        b.store(ir.Constant(f32, 0.0), out_p)
        b.store(b.fmul(new_pot, ir.Constant(f32, 0.95)), pot_p)
        b.branch(end)

        b.position_at_end(end)
        out_v = b.load(out_p)
        b.ret(
            b.select(
                b.fcmp_ordered(">", out_v, ir.Constant(f32, 0.0)),
                ir.Constant(i32, 1),
                ir.Constant(i32, 0),
            )
        )

    def _emit_main(self, mod, ir, i32, void):
        fn = ir.Function(mod, ir.FunctionType(i32, []), name="main")
        b = ir.IRBuilder(fn.append_basic_block("entry"))
        if self.module.regions and self.module.neurons:
            r = self.module.regions[0]
            nt = r.neuron_type
            neuron = next(n for n in self.module.neurons if n.name == nt)
            ty = self._neuron_ty(ir, neuron)
            arr = ir.GlobalVariable(mod, ir.ArrayType(ty, 1), name="region_neuron0")
            arr.linkage = "internal"
            init_fn = mod.get_global(f"init_{nt}")
            proc_fn = mod.get_global(f"process_{nt}")
            ptr = b.gep(arr, [ir.Constant(i32, 0), ir.Constant(i32, 0)])
            b.call(init_fn, [ptr])
            strength = b.alloca(ir.FloatType())
            b.store(ir.Constant(ir.FloatType(), 0.5), strength)
            b.call(proc_fn, [ptr, strength, ir.Constant(i32, 1)])
        b.ret(ir.Constant(i32, 0))

    def _mir_to_llvm_type(self, type_str, ir, f32, i32):
        t = type_str.lower() if type_str else "void"
        if t in ("int", "i32", "bool"):
            return i32
        elif t in ("float", "f32"):
            return f32
        elif t in ("string", "str"):
            return ir.IntType(8).as_pointer()
        return f32

    def _cast_to(self, builder, val, target_type, ir, f32, i32):
        if val.type == target_type:
            return val
        if val.type == f32 and target_type == i32:
            return builder.fptosi(val, i32)
        if val.type == i32 and target_type == f32:
            return builder.sitofp(val, f32)
        return val

    def _emit_expr(self, builder, expr, func, mod, ir, f32, i32, syms):
        if expr is None:
            return ir.Constant(i32, 0)
        typename = type(expr).__name__
        if typename == "Literal":
            val = expr.value
            if isinstance(val, bool):
                return ir.Constant(i32, int(val))
            elif isinstance(val, int):
                return ir.Constant(i32, val)
            elif isinstance(val, float):
                return ir.Constant(f32, val)
            elif isinstance(val, str):
                return ir.Constant(ir.IntType(8).as_pointer(), None)
            return ir.Constant(f32, float(val))
        elif typename == "Identifier":
            name = expr.name
            if name in syms:
                return builder.load(syms[name])
            return ir.Constant(i32, 0)
        elif typename == "BinaryOp":
            left = self._emit_expr(builder, expr.left, func, mod, ir, f32, i32, syms)
            right = self._emit_expr(builder, expr.right, func, mod, ir, f32, i32, syms)
            is_float = left.type == f32
            op = expr.op
            if op == "+":
                return builder.fadd(left, right) if is_float else builder.add(left, right)
            elif op == "-":
                return builder.fsub(left, right) if is_float else builder.sub(left, right)
            elif op == "*":
                return builder.fmul(left, right) if is_float else builder.mul(left, right)
            elif op == "/":
                return builder.fdiv(left, right) if is_float else builder.sdiv(left, right)
            elif op == "==":
                c = builder.fcmp_ordered("==", left, right) if is_float else builder.icmp_signed("==", left, right)
                return builder.zext(c, i32)
            elif op == "!=":
                c = builder.fcmp_ordered("!=", left, right) if is_float else builder.icmp_signed("!=", left, right)
                return builder.zext(c, i32)
            elif op == "<":
                c = builder.fcmp_ordered("<", left, right) if is_float else builder.icmp_signed("<", left, right)
                return builder.zext(c, i32)
            elif op == ">":
                c = builder.fcmp_ordered(">", left, right) if is_float else builder.icmp_signed(">", left, right)
                return builder.zext(c, i32)
            elif op == "<=":
                c = builder.fcmp_ordered("<=", left, right) if is_float else builder.icmp_signed("<=", left, right)
                return builder.zext(c, i32)
            elif op == ">=":
                c = builder.fcmp_ordered(">=", left, right) if is_float else builder.icmp_signed(">=", left, right)
                return builder.zext(c, i32)
            return left
        elif typename == "UnaryOp":
            operand = self._emit_expr(builder, expr.operand, func, mod, ir, f32, i32, syms)
            if expr.op == "-":
                return builder.fneg(operand) if operand.type == f32 else builder.neg(operand)
            elif expr.op == "!":
                zero = ir.Constant(i32, 0)
                return builder.zext(builder.icmp_signed("==", operand, zero), i32)
            return operand
        elif typename == "Call":
            callee = expr.name
            if callee in mod.global_values:
                fn = mod.get_global(callee)
                args = [self._emit_expr(builder, a, func, mod, ir, f32, i32, syms) for a in expr.args]
                return builder.call(fn, args)
            return ir.Constant(i32, 0)
        return ir.Constant(i32, 0)

    def _emit_stmt(self, builder, stmt, func, mod, ir, f32, i32, syms):
        if stmt is None:
            return
        typename = type(stmt).__name__
        if typename == "VarDecl":
            self._emit_var_decl(builder, stmt, func, mod, ir, f32, i32, syms)
        elif typename == "IfStmt":
            self._emit_if(builder, stmt, func, mod, ir, f32, i32, syms)
        elif typename == "ForStmt":
            self._emit_for(builder, stmt, func, mod, ir, f32, i32, syms)
        elif typename == "WhileStmt":
            self._emit_while(builder, stmt, func, mod, ir, f32, i32, syms)
        elif typename == "ReturnStmt":
            self._emit_return(builder, stmt, func, mod, ir, f32, i32, syms)
        elif typename == "Assignment":
            name = stmt.target
            val = self._emit_expr(builder, stmt.value, func, mod, ir, f32, i32, syms)
            if name in syms:
                builder.store(val, syms[name])

    def _emit_var_decl(self, builder, stmt, func, mod, ir, f32, i32, syms):
        name = stmt.name
        llvm_type = self._mir_to_llvm_type(stmt.type.name if stmt.type else "f32", ir, f32, i32)
        ptr = builder.alloca(llvm_type, name=name)
        syms[name] = ptr
        if stmt.value:
            val = self._emit_expr(builder, stmt.value, func, mod, ir, f32, i32, syms)
            val = self._cast_to(builder, val, llvm_type, ir, f32, i32)
            builder.store(val, ptr)

    def _emit_return(self, builder, stmt, func, mod, ir, f32, i32, syms):
        if stmt.value:
            val = self._emit_expr(builder, stmt.value, func, mod, ir, f32, i32, syms)
            builder.ret(val)
        else:
            builder.ret_void()

    def _emit_if(self, builder, stmt, func, mod, ir, f32, i32, syms):
        cond_val = self._emit_expr(builder, stmt.condition, func, mod, ir, f32, i32, syms)
        cond_i1 = builder.trunc(cond_val, ir.IntType(1)) if cond_val.type != ir.IntType(1) else cond_val
        then_bb = func.append_basic_block("then")
        has_else = stmt.else_block is not None
        else_bb = func.append_basic_block("else") if has_else else None
        merge_bb = func.append_basic_block("merge")
        if has_else:
            builder.cbranch(cond_i1, then_bb, else_bb)
        else:
            builder.cbranch(cond_i1, then_bb, merge_bb)
        builder.position_at_end(then_bb)
        for s in stmt.then_block.statements:
            self._emit_stmt(builder, s, func, mod, ir, f32, i32, syms)
        if not builder.block.is_terminated:
            builder.branch(merge_bb)
        if has_else:
            builder.position_at_end(else_bb)
            for s in stmt.else_block.statements:
                self._emit_stmt(builder, s, func, mod, ir, f32, i32, syms)
            if not builder.block.is_terminated:
                builder.branch(merge_bb)
        builder.position_at_end(merge_bb)

    def _emit_for(self, builder, stmt, func, mod, ir, f32, i32, syms):
        loop_bb = func.append_basic_block("loop")
        body_bb = func.append_basic_block("body")
        end_bb = func.append_basic_block("end")
        start_val = self._emit_expr(builder, stmt.start, func, mod, ir, f32, i32, syms)
        end_val = self._emit_expr(builder, stmt.end, func, mod, ir, f32, i32, syms)
        loop_var = builder.alloca(i32, name=stmt.var)
        syms[stmt.var] = loop_var
        builder.store(start_val, loop_var)
        builder.branch(loop_bb)
        builder.position_at_end(loop_bb)
        iv = builder.load(loop_var)
        builder.cbranch(builder.icmp_signed("<", iv, end_val), body_bb, end_bb)
        builder.position_at_end(body_bb)
        for s in stmt.body.statements:
            self._emit_stmt(builder, s, func, mod, ir, f32, i32, syms)
        if not builder.block.is_terminated:
            builder.store(builder.add(builder.load(loop_var), ir.Constant(i32, 1)), loop_var)
            builder.branch(loop_bb)
        builder.position_at_end(end_bb)

    def _emit_while(self, builder, stmt, func, mod, ir, f32, i32, syms):
        cond_bb = func.append_basic_block("cond")
        body_bb = func.append_basic_block("body")
        end_bb = func.append_basic_block("end")
        builder.branch(cond_bb)
        builder.position_at_end(cond_bb)
        cond_val = self._emit_expr(builder, stmt.condition, func, mod, ir, f32, i32, syms)
        cond_i1 = builder.trunc(cond_val, ir.IntType(1)) if cond_val.type != ir.IntType(1) else cond_val
        builder.cbranch(cond_i1, body_bb, end_bb)
        builder.position_at_end(body_bb)
        for s in stmt.body.statements:
            self._emit_stmt(builder, s, func, mod, ir, f32, i32, syms)
        if not builder.block.is_terminated:
            builder.branch(cond_bb)
        builder.position_at_end(end_bb)

    def _emit_mir_function(self, mod, ir, f32, i32, void, mir_func):
        ret_type = self._mir_to_llvm_type(mir_func.return_type, ir, f32, i32)
        param_types = [self._mir_to_llvm_type(t, ir, f32, i32) for _, t in mir_func.params]
        fn_ty = ir.FunctionType(ret_type, param_types)
        fn = ir.Function(mod, fn_ty, name=mir_func.name)
        entry = fn.append_basic_block("entry")
        builder = ir.IRBuilder(entry)
        syms = {}
        for i, (name, t) in enumerate(mir_func.params):
            llvm_type = self._mir_to_llvm_type(t, ir, f32, i32)
            ptr = builder.alloca(llvm_type, name=name)
            builder.store(fn.args[i], ptr)
            syms[name] = ptr
        for stmt in mir_func.body:
            self._emit_stmt(builder, stmt, fn, mod, ir, f32, i32, syms)
        if not builder.block.is_terminated:
            if mir_func.return_type == "void":
                builder.ret_void()
            else:
                builder.ret(ir.Constant(ret_type, 0))

    def compile_to_object(self, llvm_ir: str | None = None) -> bytes:
        self._ensure_llvm()
        if llvm_ir is None:
            llvm_ir = self.generate()
        mod = self._llvm.parse_assembly(llvm_ir)
        mod.verify()
        target = self._llvm.Target.from_default_triple()
        return target.create_target_machine().emit_object(mod)

    def optimize(self, llvm_ir: str, opt_level: int = 3) -> str:
        self._ensure_llvm()
        mod = self._llvm.parse_assembly(llvm_ir)
        pmb = self._llvm.create_pass_manager_builder()
        pmb.opt_level = opt_level
        pmb.loop_vectorize = True
        pmb.slp_vectorize = True
        pm = self._llvm.create_module_pass_manager()
        pmb.populate(pm)
        pm.run(mod)
        return str(mod)
