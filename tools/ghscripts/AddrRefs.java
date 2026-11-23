import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.*;
import ghidra.program.model.address.*;
import ghidra.program.model.symbol.*;
import java.util.*;

public class AddrRefs extends GhidraScript {
    public void run() throws Exception {
        for (String a : getScriptArgs()) {
            Address ad = toAddr(Long.parseLong(a, 16));
            Set<String> fs = new TreeSet<>();
            for (Reference r : getReferencesTo(ad)) {
                Function f = getFunctionContaining(r.getFromAddress());
                fs.add(f == null ? "?" + r.getFromAddress() : f.getEntryPoint() + "(" + f.getBody().getNumAddresses() + ")");
            }
            println("ADDR " + a + " -> " + fs);
        }
    }
}
