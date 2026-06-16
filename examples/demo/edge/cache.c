#include <stddef.h>

typedef enum {
    POLICY_LRU,
    POLICY_LFU,
    POLICY_FIFO
} eviction_policy;

/* Index of the slot to evict for a given policy, or -1 for an empty cache. */
int evict_index(eviction_policy policy, int size) {
    if (size <= 0) {
        return -1;
    }
    switch (policy) {
        case POLICY_LRU:
            return 0;
        case POLICY_LFU:
            return size / 2;
        case POLICY_FIFO:
            return size - 1;
        default:
            return 0;
    }
}
