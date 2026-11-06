# First Release Test Report

Date: 2026-11-06 (Asia/Shanghai)

## Deployment

- URL: `http://192.168.31.12:18080`
- Host: Ubuntu 24.04 x86_64, Docker 29.1.2
- Compose: `awardcollection-v1-test`
- Services: PostgreSQL, Django API, persistent worker, Nginx/Pure Admin

## Passed

- 26 local backend tests and 15 earlier PostgreSQL deployment tests.
- Pure Admin typecheck and cleanroom production build without Mock APIs.
- Real browser login, competition/batch views, template/seal pages, certificate archive and public/admin verification.
- Two real sample certificates with PDF, PNG and two incremental pyHanko signatures each.
- Local validation now asserts both incremental signatures are mathematically intact and valid; the expected self-signed trust-chain warning remains.
- Role isolation: unrelated account receives an empty archive and HTTP 403 for direct downloads.
- Revocation: partial approval keeps the certificate active; all original departments approving changes it to void.
- One-time captcha: first query succeeds and the reused answer returns HTTP 400.
- Backup, checksum, isolated restore and full Compose container recreation.

## Scale Test

Batch 2, the synthetic 5000-team batch, completed on the target PostgreSQL deployment. The persisted task is `done` with `processed=5000`, `total=5000`, and no error. There are 5000 certificate records, 5000 PDF files, and 5000 PNG files. The wall-clock span from task creation to completion was 2:09:52.557 and includes recovery/retry time. Three sampled PDFs matched their database digests and each contained two signature fields. Query response during generation was not measured and is not claimed as passed.

## Remaining Limitation

- The new template renderer, batch resource selection, management screens, emergency UI, dashboard, lease-safe publication, and cleanup command pass local tests/builds but are not yet deployed to the target containers because the encrypted 1Panel credential file is absent on this workstation.
- The online health endpoint still has the old response shape without the new build-version field, confirming that the target API remains on the prior image.
- Backups are currently on the same physical server.
