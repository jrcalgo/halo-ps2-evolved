#include "prefix.h"
#include "integer_math.h"
#include <stddef.h>

_Static_assert(sizeof(point2d) == 4, "Xbox point layout");
_Static_assert(sizeof(rectangle2d) == 8, "Xbox rectangle layout");
_Static_assert(offsetof(rectangle2d, x0) == 2 && offsetof(rectangle2d, x1) == 6, "Xbox rectangle field order");
_Static_assert(sizeof(pixel32) == 4, "Xbox pixel width");

char temporary[1024];

char *probe_csprintf(char *buffer, const char *format, ...)
{
    va_list arguments;
    va_start(arguments, format);
    vsnprintf(buffer, sizeof(temporary), format, arguments);
    va_end(arguments);
    return buffer;
}

void probe_assert(const char *file, int line, const char *expression)
{
    fprintf(stderr, "%s:%d assertion: %s\n", file, line, expression);
    abort();
}

void probe_warn(const char *file, int line, const char *message)
{
    fprintf(stderr, "%s:%d warning: %s\n", file, line, message);
}

#define CHECK(expression) do { if (!(expression)) { fprintf(stderr, "check failed: %s line=%d\n", #expression, __LINE__); return 1; } } while (0)

int main(void)
{
    rectangle2d a, b, result;
    point2d point;
    unsigned long left[3] = {0x80000001UL, 0xAAAAAAAAUL, 0x12345678UL};
    unsigned long right[3] = {0x80000000UL, 0x55555555UL, 0UL};
    unsigned long output[3] = {0UL, 0UL, 0xDEADBEEFUL};
    unsigned long roots[] = {0UL, 1UL, 2UL, 3UL, 255UL, 65535UL};
    unsigned int i;

    CHECK(set_rectangle2d(&a, 1, 2, 11, 22) == &a);
    CHECK(rectangle2d_width(&a) == 10 && rectangle2d_height(&a) == 20);
    set_rectangle2d(&b, 5, 5, 20, 30);
    CHECK(intersect_rectangles2d(&a, &b, &result));
    CHECK(result.x0 == 5 && result.y0 == 5 && result.x1 == 11 && result.y1 == 22);
    set_point2d(&point, 1, 2);
    CHECK(point2d_in_rectangle2d(&a, &point));
    set_point2d(&point, 11, 2);
    CHECK(!point2d_in_rectangle2d(&a, &point));
    set_point2d(&point, 1, 22);
    CHECK(!point2d_in_rectangle2d(&a, &point));
    set_rectangle2d(&b, 11, 2, 12, 22);
    CHECK(!intersect_rectangles2d(&a, &b, &result));
    CHECK(result.x0 == 0 && result.y0 == 0 && result.x1 == 0 && result.y1 == 0);
    for (i = 0; i < 32; ++i) CHECK(floor_log2(1UL << i) == (short)i);
    for (i = 1; i < 16; ++i) CHECK(ceiling_log2(1UL << i) == (short)i);
    for (i = 0; i < sizeof(roots) / sizeof(roots[0]); ++i)
        CHECK(integer_square_root(roots[i] * roots[i]) == roots[i]);
    CHECK(integer_square_root(0xFFFFFFFFUL) == 65536UL);
    CHECK(bit_vector_and(33, left, right, output));
    CHECK(output[0] == 0x80000000UL && output[1] == 0UL && output[2] == 0xDEADBEEFUL);
    bit_vector_or(33, left, right, output);
    CHECK(output[0] == 0x80000001UL && output[1] == 0xFFFFFFFFUL);
    bit_vector_not(33, left, output);
    CHECK(output[0] == 0x7FFFFFFEUL && output[1] == 0x55555555UL && output[2] == 0xDEADBEEFUL);
    CHECK(!bit_vector_and(0, left, right, output));
    puts("{\"fixture\":\"integer_math\",\"abi\":\"ILP32\",\"status\":\"passed\"}");
    return 0;
}
