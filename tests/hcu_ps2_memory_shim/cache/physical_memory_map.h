#ifndef HCU_PS2_MEMORY_TEST_PHYSICAL_MEMORY_MAP_H
#define HCU_PS2_MEMORY_TEST_PHYSICAL_MEMORY_MAP_H

void physical_memory_allocate(void);
void physical_memory_free(void);
int physical_memory_bind_game_state(void *base, unsigned long bytes);
int physical_memory_bind_tag_cache(void *base, unsigned long bytes);
int physical_memory_bind_structure_bsp_cache(void *base, unsigned long bytes);
int physical_memory_bind_texture_cache(void *base, unsigned long bytes);
int physical_memory_bind_sound_cache(void *base, unsigned long bytes);
int physical_memory_bind_malloc_arena(void *base, unsigned long bytes);
int physical_memory_bind_tag_validation_scratch(void *base, unsigned long bytes);
int physical_memory_ready(void);
int physical_memory_bindings_locked(void);
int physical_memory_bindings_clean(void);
void *physical_memory_get_game_state_base_address(void);
unsigned long physical_memory_get_game_state_size(void);
void *physical_memory_get_tag_cache_base_address(void);
unsigned long physical_memory_get_tag_cache_size(void);
void *physical_memory_get_structure_bsp_cache_base_address(void);
unsigned long physical_memory_get_structure_bsp_cache_size(void);
void *physical_memory_get_texture_cache_base_address(void);
unsigned long physical_memory_get_texture_cache_size(void);
void *physical_memory_get_sound_cache_base_address(void);
unsigned long physical_memory_get_sound_cache_size(void);
unsigned long physical_memory_get_malloc_arena_size(void);
unsigned long tag_validate_claims_buffer_size(void);

#endif
