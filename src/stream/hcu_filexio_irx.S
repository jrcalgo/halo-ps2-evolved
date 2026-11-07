	.section .rodata.hcu_iomanx_irx,"a",@progbits
	.balign 16
	.global halo_iomanx_irx_start
halo_iomanx_irx_start:
	.incbin HALO_PS2_IOMANX_IRX
	.global halo_iomanx_irx_end
halo_iomanx_irx_end:
	/* SifExecModuleBuffer DMA-copies the image rounded up to 16 bytes. Keep
	 * the zero padding inside this object's mapped section. */
	.balign 16
	.global halo_iomanx_irx_size
halo_iomanx_irx_size:
	.long halo_iomanx_irx_end-halo_iomanx_irx_start
	.global halo_iomanx_irx_raw_size
halo_iomanx_irx_raw_size:
#ifdef HALO_PS2_IOMANX_RAW_BYTES
	.long HALO_PS2_IOMANX_RAW_BYTES
#else
	.long halo_iomanx_irx_end-halo_iomanx_irx_start
#endif

	.section .rodata.hcu_filexio_irx,"a",@progbits
	.balign 16
	.global halo_filexio_irx_start
halo_filexio_irx_start:
	.incbin HALO_PS2_FILEXIO_IRX
	.global halo_filexio_irx_end
halo_filexio_irx_end:
	.balign 16
	.global halo_filexio_irx_size
halo_filexio_irx_size:
	.long halo_filexio_irx_end-halo_filexio_irx_start
	.global halo_filexio_irx_raw_size
halo_filexio_irx_raw_size:
#ifdef HALO_PS2_FILEXIO_RAW_BYTES
	.long HALO_PS2_FILEXIO_RAW_BYTES
#else
	.long halo_filexio_irx_end-halo_filexio_irx_start
#endif
