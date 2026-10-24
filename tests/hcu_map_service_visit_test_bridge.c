/* Include the production translation unit so this fixture can call its exact
 * static HP2-to-parent callback without cloning its convention conversion. */
#include "../src/stream/hcu_map_service.c"

static unsigned test_visit_count;
static size_t test_last_sink_bytes;

typedef struct test_sink_counter {
	ctag_bsp_sink_fn sink;
	void *sink_context;
	size_t accepted_bytes;
} test_sink_counter;

static int count_sink_bytes(void *context, uint32_t offset,
	const uint8_t *bytes, size_t size)
{
	test_sink_counter *counter = (test_sink_counter *)context;
	if (!counter || !counter->sink ||
		!counter->sink(counter->sink_context, offset, bytes, size))
		return 0;
	counter->accepted_bytes += size;
	return 1;
}

extern int hcu_test_before_bsp_visit(const char *tag);
extern void hcu_test_after_bsp_visit(const char *tag, int succeeded);

int hcu_map_service_test_visit_section(void *context, const char *path,
	const char *tag, ctag_bsp_sink_fn sink, void *sink_context,
	size_t *raw_size)
{
	int succeeded;
	test_sink_counter counter;
	test_last_sink_bytes = 0;
	if (hcu_test_before_bsp_visit(tag)) {
		++test_visit_count;
		hcu_test_after_bsp_visit(tag, 0);
		return 0;
	}
	++test_visit_count;
	counter.sink = sink;
	counter.sink_context = sink_context;
	counter.accepted_bytes = 0;
	succeeded = visit_section(context, path, tag, count_sink_bytes, &counter,
		raw_size);
	test_last_sink_bytes = counter.accepted_bytes;
	hcu_test_after_bsp_visit(tag, succeeded);
	return succeeded;
}

void hcu_map_service_test_reset_visit_count(void)
{
	test_visit_count = 0;
}

unsigned hcu_map_service_test_visit_count(void)
{
	return test_visit_count;
}

size_t hcu_map_service_test_last_sink_bytes(void)
{
	return test_last_sink_bytes;
}
