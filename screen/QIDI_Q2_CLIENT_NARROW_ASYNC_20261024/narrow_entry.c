/* Offline alternative for history bridge's final async call ONLY (0x4f7c50).
 * Never a global async replacement. Normal paths of the reviewed callee do
 * not call C++ or execute the queued callback. A nonreturning factory OOM
 * path and abnormal unwinding are outside this bounded prototype contract.
 * This object has no production bindings, loader, patcher or installer. */
#include <pthread.h>
#include <stdlib.h>

extern pthread_mutex_t q2_gui_mutex;
extern unsigned long q2_original_async(void (*callback)(void *), void *argument);

unsigned long q2_history_async_entry(void (*callback)(void *), void *argument) {
 if (pthread_mutex_lock(&q2_gui_mutex) != 0) abort();
 unsigned long result = q2_original_async(callback, argument);
 if (pthread_mutex_unlock(&q2_gui_mutex) != 0) abort();
 return result;
}
