#include "hcu_chain_variant.h"

#include <stdio.h>
#include <string.h>

int main(void)
{
	unsigned char rules[HCU_CHAIN_RULE_BYTES];
	unsigned char parsed[HCU_CHAIN_RULE_BYTES];
	char text[80];
	int i;

	if (HCU_CHAIN_RULE_BYTES != 34)
		return 1;
	for (i = 0; i < HCU_CHAIN_RULE_BYTES; ++i)
		rules[i] = (unsigned char)((i * 17) ^ 0xA5);
	rules[HCU_RULE_GAME] = 0;
	rules[HCU_RULE_TIME] = 4;
	rules[HCU_RULE_BALL_SPEED] = 2;
	if (!hcu_chain_rules_format(rules, text, (int)sizeof text))
		return 2;
	if (text[0] != 'V' || (int)strlen(text) != 1 + HCU_CHAIN_RULE_BYTES * 2)
		return 3;
	memset(parsed, 0x5A, sizeof parsed);
	if (!hcu_chain_rules_parse(text, parsed))
		return 4;
	if (memcmp(rules, parsed, sizeof rules) != 0)
		return 5;
	text[3] = 'G';
	if (hcu_chain_rules_parse(text, parsed))
		return 6;
	text[3] = 'a';
	text[1 + HCU_CHAIN_RULE_BYTES * 2] = '0';
	text[2 + HCU_CHAIN_RULE_BYTES * 2] = '\0';
	if (hcu_chain_rules_parse(text, parsed))
		return 7;
	if (hcu_chain_rules_format(rules, text, 8))
		return 8;
	printf("chain-variant-ok bytes=%d\n", HCU_CHAIN_RULE_BYTES);
	return 0;
}
