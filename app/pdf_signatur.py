"""Digitale Signatur der Beleg-PDFs (PAdES, selbst-signiert).

Zweck: Ein an den Kunden versendetes PDF soll nach dem Versand nicht unbemerkt
verändert werden können. Beim Druck wird das fertige Original-PDF mit einem
**selbst-signierten** Firmen-Zertifikat digital signiert. Wird das PDF danach
auch nur um ein Byte verändert, schlägt die Signaturprüfung im PDF-Reader fehl —
die Manipulation ist erkennbar.

Selbst-signiert heißt: der Reader zeigt „gültig, Identität nicht verifiziert"
(gelbes Warndreieck). Der Integritätsschutz wirkt trotzdem voll. Ein grünes
Häkchen bräuchte ein gekauftes Zertifikat eines Vertrauensdiensteanbieters —
dafür müsste nur die ``.p12``-Datei ausgetauscht werden, nicht dieser Code.

Pfad-Regel (CLAUDE.md): kein Pfad in der DB. Der Zertifikatpfad wird
konventionsbasiert über ``settings.signatur_zertifikat_pfad(firma)`` berechnet.

Die Bibliotheken (``pyhanko``, ``cryptography``) werden nur bei Bedarf importiert,
damit die App auch ohne sie startet. ``ist_verfuegbar()`` prüft das.
"""
from __future__ import annotations

import datetime
import os
import secrets
import tempfile

# Sichtbarer Signaturstempel: Box unten links in der Fußzeile (A4, Ursprung unten
# links, Angaben in PDF-Punkten; 1 mm ≈ 2,835 pt). Der Beleg-Footer (Bankzeile) ist
# um die Seitenmitte zentriert, die Trennlinie liegt bei ~15 mm (druck_basis.FUSS_Y),
# darunter/links bleibt Platz. Der Stempel wird auf der letzten Seite platziert.
_STEMPEL_BOX = (57, 6, 173, 40)  # x1,y1,x2,y2  ≈ 20–61 mm / 2–14 mm


def ist_verfuegbar() -> bool:
    """True, wenn pyHanko und cryptography importierbar sind."""
    try:
        import cryptography  # noqa: F401
        import pyhanko  # noqa: F401
        return True
    except Exception:  # noqa: BLE001
        return False


def _zert_subject(firma: dict):
    """X.509-Name aus den Firmenstammdaten (Firmenname, Ort, USt-ID)."""
    from cryptography import x509
    from cryptography.x509.oid import NameOID

    name = (firma.get("name") or firma.get("firmen_nr") or "Firma").strip() or "Firma"
    attrs = [x509.NameAttribute(NameOID.COMMON_NAME, name),
             x509.NameAttribute(NameOID.ORGANIZATION_NAME, name)]
    ort = (firma.get("ort") or "").strip()
    if ort:
        attrs.append(x509.NameAttribute(NameOID.LOCALITY_NAME, ort))
    land = (firma.get("land_code") or firma.get("land") or "").strip()[:2].upper()
    if len(land) == 2 and land.isalpha():
        attrs.append(x509.NameAttribute(NameOID.COUNTRY_NAME, land))
    ust = (firma.get("ust_id") or firma.get("ustid") or "").strip()
    if ust:
        attrs.append(x509.NameAttribute(NameOID.SERIAL_NUMBER, ust))
    return x509.Name(attrs)


def erzeuge_zertifikat(firma: dict, jahre: int = 10) -> str:
    """Erzeugt ein selbst-signiertes ``.p12``-Zertifikat für die Firma und legt es
    am Konventionsort ab. Gibt das **automatisch erzeugte Passwort** zurück; der
    Aufrufer speichert es (firma['signatur_cert_passwort']) über ``save_firma``.

    Wirft eine Exception bei fehlenden Bibliotheken oder Schreibfehlern — der
    UI-Aufrufer meldet das dem Benutzer.
    """
    if not ist_verfuegbar():
        raise RuntimeError(
            "Für die PDF-Signatur fehlen die Pakete 'pyhanko' und 'cryptography'. "
            "Installation: pip install pyhanko cryptography")

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives.serialization import pkcs12
    import settings

    passwort = secrets.token_urlsafe(24)
    schluessel = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = _zert_subject(firma)
    jetzt = datetime.datetime.now(datetime.timezone.utc)
    zert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(schluessel.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(jetzt - datetime.timedelta(minutes=5))
        .not_valid_after(jetzt + datetime.timedelta(days=365 * jahre))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True, content_commitment=True,
                key_encipherment=False, data_encipherment=False,
                key_agreement=False, key_cert_sign=False, crl_sign=False,
                encipher_only=False, decipher_only=False),
            critical=True)
        .sign(schluessel, hashes.SHA256())
    )
    p12 = pkcs12.serialize_key_and_certificates(
        name=b"Beleg-Signatur", key=schluessel, cert=zert, cas=None,
        encryption_algorithm=serialization.BestAvailableEncryption(passwort.encode()))

    pfad = settings.signatur_zertifikat_pfad(firma)
    os.makedirs(os.path.dirname(pfad), exist_ok=True)
    with open(pfad, "wb") as f:
        f.write(p12)
    return passwort


def zertifikat_status(firma: dict) -> dict:
    """Statusinfo für die UI: {'vorhanden': bool, 'gueltig_bis': 'YYYY-MM-DD'|'' }.
    Schlägt nie hart fehl."""
    import settings
    pfad = settings.signatur_zertifikat_pfad(firma)
    if not os.path.isfile(pfad):
        return {"vorhanden": False, "gueltig_bis": ""}
    gueltig_bis = ""
    try:
        from cryptography.hazmat.primitives.serialization import pkcs12
        passwort = (firma.get("signatur_cert_passwort") or "").encode()
        with open(pfad, "rb") as f:
            _key, cert, _cas = pkcs12.load_key_and_certificates(f.read(), passwort)
        if cert is not None:
            gueltig_bis = cert.not_valid_after_utc.strftime("%Y-%m-%d")
    except Exception:  # noqa: BLE001
        pass
    return {"vorhanden": True, "gueltig_bis": gueltig_bis}


def signiere_pdf(pdf_pfad: str, firma: dict) -> None:
    """Signiert ``pdf_pfad`` in-place (PAdES/PKCS#7) mit dem Firmen-Zertifikat.

    Wirft eine Exception bei fehlenden Paketen, fehlendem/kaputtem Zertifikat oder
    Signaturfehler — der Aufrufer (druck_beleg) protokolliert das als Fallback
    (ERROR.DB) und liefert das PDF unsigniert aus.
    """
    if not ist_verfuegbar():
        raise RuntimeError("pyhanko/cryptography nicht installiert")

    import settings
    from pyhanko.sign import signers
    from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter

    zert_pfad = settings.signatur_zertifikat_pfad(firma)
    if not os.path.isfile(zert_pfad):
        raise FileNotFoundError(zert_pfad)

    passwort = (firma.get("signatur_cert_passwort") or "").encode()
    signer = signers.SimpleSigner.load_pkcs12(pfx_file=zert_pfad, passphrase=passwort)
    if signer is None:
        raise RuntimeError("Zertifikat konnte nicht geladen werden (Passwort?)")

    from pyhanko.sign.fields import SigFieldSpec, append_signature_field
    from pyhanko.stamp import TextStampStyle

    meta = signers.PdfSignatureMetadata(
        field_name="Beleg-Signatur",
        reason="Integritaetssicherung Beleg",
        location=(firma.get("ort") or "").strip() or None)

    # Sichtbarer Stempel auf der letzten Seite (Unterzeichner aus Zertifikat + Zeit).
    import fitz
    with fitz.open(pdf_pfad) as _doc:
        letzte_seite = max(_doc.page_count - 1, 0)
    field_spec = SigFieldSpec("Beleg-Signatur", on_page=letzte_seite, box=_STEMPEL_BOX)
    stamp_style = TextStampStyle(stamp_text="Digital signiert:\n%(signer)s\n%(ts)s",
                                 timestamp_format="%d.%m.%Y %H:%M",
                                 border_color=(0.7, 0.7, 0.7))  # hellgrauer Rahmen
    pdf_signer = signers.PdfSigner(meta, signer=signer, stamp_style=stamp_style)

    # Inkrementell in eine Temp-Datei signieren, dann atomar ersetzen.
    tmp_fd, tmp_pfad = tempfile.mkstemp(suffix=".pdf",
                                        dir=os.path.dirname(pdf_pfad) or None)
    os.close(tmp_fd)
    try:
        with open(pdf_pfad, "rb") as inf, open(tmp_pfad, "wb") as outf:
            w = IncrementalPdfFileWriter(inf)
            append_signature_field(w, field_spec)
            pdf_signer.sign_pdf(w, output=outf)
        os.replace(tmp_pfad, pdf_pfad)
    finally:
        if os.path.exists(tmp_pfad):
            os.remove(tmp_pfad)
