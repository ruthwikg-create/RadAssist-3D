# RadAssist 3D Security and Patient-Data Protection

RadAssist 3D is a research/engineering workstation. It is not a certified clinical information system. Patient-data protection must be configured and verified for the deployment environment.

## Default privacy posture

- Do not commit DICOM, NIfTI, model checkpoints, case data, logs, or secrets to Git.
- Source uploads are processed in a temporary workspace and are not retained as original uploads by the case store.
- Persisted case artifacts can still contain sensitive imaging-derived information and must be protected.
- API v1 responses are marked Cache-Control: no-store.
- Browser security headers are enabled.
- API documentation is disabled by default.
- Synthetic demo mode is disabled by default.
- Case identifiers reject path traversal.
- Input manifests store hashes, sizes and extensions rather than original source filenames.
- Optional case-retention cleanup can delete old derived artifacts automatically.

## Protected deployment settings

Set:

- RADASSIST_REQUIRE_AUTH=true
- RADASSIST_API_TOKEN=<long random secret>
- RADASSIST_TRUSTED_HOSTS=<approved hostnames>
- RADASSIST_ENABLE_DOCS=false
- RADASSIST_FORCE_HTTPS=true
- RADASSIST_CASE_RETENTION_HOURS=<appropriate retention window>

The frontend can send the bearer token using NEXT_PUBLIC_RADASSIST_API_TOKEN for controlled local/research deployments. Because any NEXT_PUBLIC_* value is visible to browser users, this is not a substitute for real user authentication in a multi-user/public deployment. For that environment, put RadAssist behind an authenticated reverse proxy/identity provider and keep the backend private.

## Recommended production architecture

Do not expose the inference API directly to the public internet.

Browser
→ HTTPS reverse proxy / identity provider
→ private RadAssist frontend
→ private backend
→ isolated case storage

For PACS/DICOMweb integration, use a controlled DICOM server such as Orthanc and apply its authentication, network and TLS controls separately.

## Data handling

Before processing real patient data:

1. Confirm the dataset is authorized for the intended research use.
2. Prefer de-identified datasets for development.
3. Do not use patient names, IDs or accession numbers in filenames, logs, screenshots or issue reports.
4. Do not upload PHI to public GitHub issues or repositories.
5. Keep case storage on an encrypted disk/volume where appropriate.
6. Restrict filesystem permissions for backend/data/cases.
7. Configure retention and deletion according to the study/institution policy.
8. Back up only encrypted, access-controlled artifacts.

## DICOM export

DICOM SEG/SR output can contain identifying metadata because it references the source DICOM study. Protect exported DICOM objects as patient data. De-identification must be an explicit, validated workflow; do not assume that a derived DICOM object is automatically anonymous.

## Secrets

Never commit:

- API tokens
- passwords
- private keys
- cloud credentials
- PACS credentials
- database credentials

Use environment/secret-management facilities instead.

## Validation boundary

These controls reduce common application-level data-exposure risks but do not establish regulatory compliance, institutional privacy compliance, HIPAA/GDPR compliance, or clinical cybersecurity certification. A real deployment requires an organization-specific security/privacy assessment, threat model, penetration testing, access-control review, incident-response process and applicable regulatory controls.
