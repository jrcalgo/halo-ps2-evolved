#include <assert.h>
#include <limits.h>

int _stricmp(const char *left, const char *right);
int _strnicmp(const char *left, const char *right, unsigned long count);

int main(void)
{
	static const char high_left[] = { 'A', (char)0xC0, 0 };
	static const char high_right[] = { 'a', (char)0xE0, 0 };
	assert(_stricmp("HaloScript", "hALOsCRIPT") == 0);
	assert(_stricmp("tag-a", "tag-b") < 0);
	assert(_stricmp("tag-b", "tag-a") > 0);
	assert(_strnicmp("WEAPON_rifle", "weapon_launcher", 6) == 0);
	assert(_strnicmp("WEAPON_rifle", "weapon_launcher", 8) != 0);
	assert(_strnicmp("abc", "abcd", 3) == 0);
	assert(_strnicmp("abc", "abcd", 4) < 0);
	assert(_stricmp(high_left, high_right) != 0);
	assert(_stricmp("", "") == 0);
	(void)CHAR_BIT;
	return 0;
}
