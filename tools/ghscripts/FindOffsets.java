import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.*;
import ghidra.program.model.address.*;
import ghidra.program.model.scalar.Scalar;
import java.util.*;

public class FindOffsets extends GhidraScript {
    public void run() throws Exception {
        Set<Long> want = new HashSet<>(Arrays.asList(0x248L, 0x24cL, 0x258L));
        Map<Function, Set<Long>> hits = new LinkedHashMap<>();
        InstructionIterator it = currentProgram.getListing().getInstructions(true);
        while (it.hasNext()) {
            Instruction in = it.next();
            String m = in.getMnemonicString();
            if (!m.startsWith("ldr")) continue;
            for (int i = 0; i < in.getNumOperands(); i++) {
                for (Object o : in.getOpObjects(i)) {
                    if (o instanceof Scalar && want.contains(((Scalar) o).getUnsignedValue())) {
                        Function f = getFunctionContaining(in.getAddress());
                        if (f != null) hits.computeIfAbsent(f, k -> new TreeSet<>()).add(((Scalar) o).getUnsignedValue());
                    }
                }
            }
        }
        for (Map.Entry<Function, Set<Long>> e : hits.entrySet())
            println("HIT " + e.getKey().getEntryPoint() + " " + e.getKey().getName() + " size=" + e.getKey().getBody().getNumAddresses() + " offs=" + e.getValue());
    }
}
