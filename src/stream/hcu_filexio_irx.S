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
