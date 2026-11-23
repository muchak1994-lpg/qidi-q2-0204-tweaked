import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.*;
import ghidra.program.model.listing.*;
import ghidra.program.model.address.*;
import ghidra.program.model.symbol.*;

public class Decomp extends GhidraScript {
    public void run() throws Exception {
        DecompInterface d = new DecompInterface();
        d.openProgram(currentProgram);
        for (String a : getScriptArgs()) {
            Address ad = toAddr(Long.parseLong(a, 16));
            Function f = getFunctionContaining(ad); if (f == null) { disassemble(ad); f = createFunction(ad, null); }
            if (f == null) { println("NOFUNC " + a); continue; }
            DecompileResults r = d.decompileFunction(f, 120, monitor);
            println("=====FUNC " + f.getEntryPoint() + " " + f.getName());
            for (Reference ref : getReferencesTo(f.getEntryPoint())) println("CALLER " + ref.getFromAddress());
            println(r.decompileCompleted() ? r.getDecompiledFunction().getC() : "FAILED");
        }
    }
}
