/*
 * HCU fixed-UTC time conversion.
 *
 * The PS2 guest has no TZ setting, so newlib's local zone is GMT with no offset
 * and no daylight saving: local time equals UTC. These definitions replace
 * localtime, localtime_r and mktime so that libc's localtime.o, mktime.o and
 * tzset.o/tzset_r.o are not linked. tzset_r is the only reference to scanf
 * (about 20 KB of the production ELF).
 */
#include <time.h>
#include <stdint.h>

/* Days since 1970-01-01 in the proleptic Gregorian calendar; m is 1..12. */
static int64_t hcu_tz_days_from_civil(int64_t y, int64_t m, int64_t d)
{
	int64_t era;
	int64_t yoe;
	int64_t doy;
	int64_t doe;

	if (m <= 2) {
		y -= 1;
	}
	era = (y >= 0 ? y : y - 399) / 400;
	yoe = y - era * 400;
	doy = (153 * (m > 2 ? m - 3 : m + 9) + 2) / 5 + d - 1;
	doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;
	return era * 146097 + doe - 719468;
}

struct tm *localtime_r(const time_t *timer, struct tm *result)
{
	return gmtime_r(timer, result);
}

struct tm *localtime(const time_t *timer)
{
	static struct tm result;

	return gmtime_r(timer, &result);
}

time_t mktime(struct tm *tm)
{
	int64_t year = (int64_t)tm->tm_year + 1900;
	int64_t mon = tm->tm_mon;
	int64_t adjust;
	int64_t days;
	int64_t seconds;
	time_t result;

	/* Normalise the month into 0..11, carrying whole years. */
	adjust = mon >= 0 ? mon / 12 : -((-mon + 11) / 12);
	year += adjust;
	mon -= adjust * 12;

	days = hcu_tz_days_from_civil(year, mon + 1, 1) + (tm->tm_mday - 1);
	seconds = days * 86400 + (int64_t)tm->tm_hour * 3600 + (int64_t)tm->tm_min * 60 + tm->tm_sec;
	result = (time_t)seconds;
	/* As mktime does, store the normalised fields back into tm. */
	gmtime_r(&result, tm);
	return result;
}
