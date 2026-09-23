PREFIX      ?= $(HOME)/.local
DATADIR     ?= $(PREFIX)/share
BINDIR      ?= $(PREFIX)/bin
APPDIR      := $(DATADIR)/zarch-cleaner
ICONDIR     := $(DATADIR)/icons/hicolor/scalable/apps
APPDIR_DESKTOP := $(DATADIR)/applications
METAINFODIR := $(DATADIR)/metainfo

APP_ID      := io.github.adamzakys.ZarchCleaner
PYTHON      ?= /usr/bin/python3
POLKIT_DIR  ?= /usr/share/polkit-1/actions

LAUNCHER    := $(BINDIR)/zarch-cleaner

.PHONY: help run test install uninstall install-polkit clean

help:
	@echo "Target yang tersedia:"
	@echo "  make run              - jalankan langsung dari kode sumber"
	@echo "  make test             - jalankan test (unittest)"
	@echo "  make install          - pasang ke $(PREFIX)"
	@echo "  make uninstall        - hapus pemasangan dari $(PREFIX)"
	@echo "  make install-polkit   - pasang kebijakan polkit (butuh root)"
	@echo "  make clean            - hapus berkas sementara"

run:
	PYTHONPATH=. $(PYTHON) -m zarchcleaner

test:
	$(PYTHON) -m unittest discover -s tests -t . -v

install:
	@echo "Memasang aplikasi ke $(APPDIR)"
	install -d $(DESTDIR)$(APPDIR) $(DESTDIR)$(BINDIR) \
	           $(DESTDIR)$(APPDIR_DESKTOP) $(DESTDIR)$(ICONDIR) $(DESTDIR)$(METAINFODIR)
	rm -rf $(DESTDIR)$(APPDIR)/zarchcleaner
	cp -r zarchcleaner $(DESTDIR)$(APPDIR)/zarchcleaner
	find $(DESTDIR)$(APPDIR) -name '__pycache__' -type d -prune -exec rm -rf {} +
	install -m 0755 data/zarch-cleaner.launcher $(DESTDIR)$(LAUNCHER)
	sed 's|@EXEC@|$(LAUNCHER)|g' \
	    data/$(APP_ID).desktop.in > $(DESTDIR)$(APPDIR_DESKTOP)/$(APP_ID).desktop
	install -m 0644 data/icons/hicolor/scalable/apps/$(APP_ID).svg \
	    $(DESTDIR)$(ICONDIR)/$(APP_ID).svg
	install -m 0644 data/$(APP_ID).metainfo.xml \
	    $(DESTDIR)$(METAINFODIR)/$(APP_ID).metainfo.xml
	-update-desktop-database $(DESTDIR)$(APPDIR_DESKTOP) 2>/dev/null || true
	-gtk-update-icon-cache -q -t -f $(DESTDIR)$(DATADIR)/icons/hicolor 2>/dev/null || true
	@echo
	@echo "Selesai. Jalankan dengan: zarch-cleaner"
	@echo "Pastikan $(BINDIR) ada di PATH."

uninstall:
	rm -rf $(DESTDIR)$(APPDIR)
	rm -f $(DESTDIR)$(LAUNCHER)
	rm -f $(DESTDIR)$(APPDIR_DESKTOP)/$(APP_ID).desktop
	rm -f $(DESTDIR)$(ICONDIR)/$(APP_ID).svg
	rm -f $(DESTDIR)$(METAINFODIR)/$(APP_ID).metainfo.xml
	-update-desktop-database $(DESTDIR)$(APPDIR_DESKTOP) 2>/dev/null || true
	@echo "Pemasangan dihapus. Konfigurasi di ~/.config/zarch-cleaner dibiarkan."

install-polkit:
	@echo "Memasang kebijakan polkit ke $(POLKIT_DIR) (butuh hak akses root)"
	install -d $(DESTDIR)$(POLKIT_DIR)
	sed 's|@HELPER@|$(APPDIR)/zarchcleaner/helper.py|g' \
	    data/$(APP_ID).policy.in > /tmp/$(APP_ID).policy
	sudo install -m 0644 /tmp/$(APP_ID).policy $(DESTDIR)$(POLKIT_DIR)/$(APP_ID).policy
	rm -f /tmp/$(APP_ID).policy
	@echo "Terpasang. Lihat komentar di berkas policy untuk batasannya."

clean:
	find . -name '__pycache__' -type d -prune -exec rm -rf {} +
	find . -name '*.pyc' -delete
	rm -rf build dist *.egg-info
