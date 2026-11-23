import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.*;
import ghidra.program.model.address.*;
import ghidra.program.model.symbol.*;
import java.util.*;

public class StrRefs extends GhidraScript {
    public void run() throws Exception {
        List<String> pats = Arrays.asList(getScriptArgs());
        for (Data d : currentProgram.getListing().getDefinedData(true)) {
            Object v = d.getValue();
            if (!(v instanceof String)) continue;
            String s = (String) v;
            for (String p : pats) {
                if (s.contains(p)) {
                    Set<String> fs = new TreeSet<>();
                    for (Reference r : getReferencesTo(d.getAddress())) {
                        Function f = getFunctionContaining(r.getFromAddress());
                        fs.add(f == null ? "?" + r.getFromAddress() : f.getEntryPoint() + "(" + f.getBody().getNumAddresses() + ")");
                    }
                    println("STR " + d.getAddress() + " [" + s.replace("\n","\n") + "] -> " + fs);
                }
            }
        }
    }
}
