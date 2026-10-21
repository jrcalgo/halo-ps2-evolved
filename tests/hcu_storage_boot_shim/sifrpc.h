#ifndef TEST_SIFRPC_H
#define TEST_SIFRPC_H

#define SIF_RPC_M_NOWAIT 0x01
typedef struct {
	void *server;
} SifRpcClientData_t;

int sceSifBindRpc(SifRpcClientData_t *client, int server_id, int mode);

#endif
