	.section .rodata.hcu_libsd_irx,"a",@progbits
	.balign 16
	.global halo_libsd_irx_start
halo_libsd_irx_start:
	.incbin HALO_PS2_LIBSD_IRX
	.global halo_libsd_irx_end
halo_libsd_irx_end:
	.balign 16
	.global halo_libsd_irx_size
halo_libsd_irx_size:
	.long halo_libsd_irx_end-halo_libsd_irx_start

	.section .rodata.hcu_sdrdrv_irx,"a",@progbits
	.balign 16
	.global halo_sdrdrv_irx_start
halo_sdrdrv_irx_start:
	.incbin HALO_PS2_SDRDRV_IRX
	.global halo_sdrdrv_irx_end
halo_sdrdrv_irx_end:
	.balign 16
	.global halo_sdrdrv_irx_size
halo_sdrdrv_irx_size:
	.long halo_sdrdrv_irx_end-halo_sdrdrv_irx_start
