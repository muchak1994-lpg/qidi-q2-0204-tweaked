# Ghidra scripts used for the audit of the screen program (qidiclient)

Four small GhidraScript files (Java) that were used with Ghidra 12.2 (needs a JDK 21 or newer) in headless mode to read QIDI's
screen program `qidiclient` (aarch64) for `docs/QIDICLIENT_AUDIT.md`. They contain no QIDI code; they only ask Ghidra questions.
No QIDI binary and no Ghidra project is stored in this repository: get the binary from your own printer or from QIDI's package.

| Script | Arguments | What it prints |
|---|---|---|
| `StrRefs.java` | text patterns | every defined string containing a pattern, with the functions that refer to it |
| `AddrRefs.java` | addresses (hex) | the functions that refer to each address (with their size) |
| `Decomp.java` | addresses (hex) | the decompiled C of the function containing each address, plus its callers |
| `FindOffsets.java` | none (offsets are in the file) | functions that load a struct field at the given offsets (`ldr ... #0x248` etc.) |

Run (after importing the binary into a project and analysing it once):

```
analyzeHeadless <project folder> <project name> -process <binary name> -noanalysis -scriptPath tools/ghscripts -postScript Decomp.java 55e090
```

Addresses are Ghidra virtual addresses (for this binary the file offset is the address minus 0x400000). Everything the scripts print is
a reading aid: check a claim against the disassembly before relying on it (the audit marks each statement as proof, deduction or guess).
