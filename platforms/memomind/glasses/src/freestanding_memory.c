#include <stddef.h>

void *memcpy(void *destination, const void *source, size_t count)
{
    unsigned char *output = (unsigned char *)destination;
    const unsigned char *input = (const unsigned char *)source;
    size_t index;
    for (index = 0U; index < count; ++index) output[index] = input[index];
    return destination;
}

void *memset(void *destination, int value, size_t count)
{
    unsigned char *output = (unsigned char *)destination;
    size_t index;
    for (index = 0U; index < count; ++index)
        output[index] = (unsigned char)value;
    return destination;
}
