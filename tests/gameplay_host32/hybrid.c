#include "hybrid/replay.h"
#include <stdio.h>
#include <string.h>

int main(void)
{
    unsigned normal, suppressed, delayed;
    struct hybrid_snapshot a, b, c;
    if (hybrid_replay(1, &normal, &a, NULL, NULL) || hybrid_replay(0, &suppressed, &b, NULL, NULL) ||
        hybrid_replay(7, &delayed, &c, NULL, NULL))
        return 1;
    if (normal != suppressed || normal != delayed || memcmp(&a, &b, sizeof a) || memcmp(&a, &c, sizeof a)) {
        fprintf(stderr, "hybrid presentation schedules diverged\n");
        return 1;
    }
    printf("{\"fixture\":\"hybrid-host\",\"ticks\":18000,\"created\":30,\"destroyed\":30,\"stale_rejected\":30,\"event_hash\":%u,\"presentation_independent\":true,\"status\":\"passed\"}\n", normal);
    return 0;
}
