PROJECT_NAME := firmware

.PHONY: all clean fullclean flash monitor menuconfig help tidbyt-gen1 tidbyt-gen1_swap tidbyt-gen2 pixora-s3 pixora-s3-wide pixoticker matrixportal-s3 matrixportal-s3-waveshare matrixportal-s3-128x32

help:
	@echo "Pixora Firmware Build System"
	@echo ""
	@echo "Targets:"
	@echo "  all              Build for the currently configured board"
	@echo "  clean            Clean the build directory"
	@echo "  fullclean        Delete the build directory"
	@echo "  flash            Flash the firmware"
	@echo "  monitor          Monitor the serial output"
	@echo "  menuconfig       Open the configuration menu"
	@echo ""
	@echo "Device Specific Builds (Builds, but does not flash):"
	@echo "  tidbyt-gen1              Build for Tidbyt Gen 1"
	@echo "  tidbyt-gen1_swap         Build for Tidbyt Gen 1 (Swap Colors)"
	@echo "  tidbyt-gen2              Build for Tidbyt Gen 2"
	@echo "  pixora-s3                 Build for Pixora S3"
	@echo "  pixora-s3-wide            Build for Pixora S3 Wide"
	@echo "  pixoticker               Build for Pixoticker"
	@echo "  matrixportal-s3          Build for MatrixPortal S3"
	@echo "  matrixportal-s3-waveshare Build for MatrixPortal S3 (Waveshare)"
	@echo "  matrixportal-s3-128x32   Build for MatrixPortal S3 128x32"

IDFPY := $(shell which idf.py)
PYTHON := python3

all:
	$(PYTHON) $(IDFPY) build

clean:
	$(PYTHON) $(IDFPY) clean

fullclean:
	$(PYTHON) $(IDFPY) fullclean
	rm -f sdkconfig

flash:
	$(PYTHON) $(IDFPY) flash

monitor:
	$(PYTHON) $(IDFPY) monitor

menuconfig:
	$(PYTHON) $(IDFPY) menuconfig

# Macro for device-specific builds
# Usage: $(call build_device,<chip>,<defaults_file>,<device_name>)
define build_device
	rm -f sdkconfig
	IDF_TARGET=$(1) $(PYTHON) $(IDFPY) -D SDKCONFIG_DEFAULTS="sdkconfig.defaults;$(2)" set-target $(1)
	IDF_TARGET=$(1) $(PYTHON) $(IDFPY) build
	cd build && esptool.py --chip $(1) merge_bin -o merged_firmware.bin @flash_args
	$(eval FW_VERSION := $(shell sed -n 's/.*FIRMWARE_VERSION "\([^"]*\)".*/\1/p' main/version.h 2>/dev/null || echo local))
	cp build/firmware.bin build/pixora-v$(FW_VERSION)-$(3)-ota-firmware.bin
	cp build/merged_firmware.bin build/pixora-v$(FW_VERSION)-$(3)-usb-full-flash.bin
	cp build/bootloader/bootloader.bin build/pixora-v$(FW_VERSION)-$(3)-bootloader.bin
	cp build/partition_table/partition-table.bin build/pixora-v$(FW_VERSION)-$(3)-partition-table.bin
	cp build/flash_args build/pixora-v$(FW_VERSION)-$(3)-flash-args.txt
endef

# Device Specific Targets
tidbyt-gen1:
	$(call build_device,esp32,sdkconfig.defaults.tidbyt-gen1,tidbyt)

tidbyt-gen1_swap:
	$(call build_device,esp32,sdkconfig.defaults.tidbyt-gen1_swap,tidbyt)

tidbyt-gen2:
	$(call build_device,esp32,sdkconfig.defaults.tidbyt-gen2,tidbyt)

pixora-s3:
	$(call build_device,esp32s3,sdkconfig.defaults.pixora-s3,64x32)

pixora-s3-wide:
	$(call build_device,esp32s3,sdkconfig.defaults.pixora-s3-wide,128x32)

pixoticker:
	$(call build_device,esp32,sdkconfig.defaults.pixoticker,tidbyt)

matrixportal-s3:
	$(call build_device,esp32s3,sdkconfig.defaults.matrixportal-s3,64x32)

matrixportal-s3-waveshare:
	$(call build_device,esp32s3,sdkconfig.defaults.matrixportal-s3-waveshare,64x32)

matrixportal-s3-128x32:
	$(call build_device,esp32s3,sdkconfig.defaults.matrixportal-s3-128x32,128x32)
