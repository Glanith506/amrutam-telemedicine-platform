# Frontend usage

## Sign in as the patient you already registered

Click **Sign in**, enter the exact email and password you registered in Swagger, and submit.
Leave the authenticator field empty if that account has not enabled MFA. Sessions last in
memory only: refreshing the page signs you out, so sign in again if needed.
If the account you registered was patient1@example.com, use that exact address; if you used
another email, use that one. No default passwords or reusable admin credentials ship here.

## Patient screens

- Overview: personal appointment totals and doctor directory.
- Find a doctor: filter by specialty and maximum price in rupees.
- View available times: select a future slot, then confirm booking.
- My appointments: review dates/status, cancel a booked appointment and read issued prescriptions.
- Account & security: see your user ID, configure MFA, sign out.

The automated backend demo consumes its doctor slots, so its demo doctors may have **no open
slots**. That is an expected empty state. A doctor must publish new availability before a
patient can book. Re-running the old demo does not create reusable UI login credentials.

## Set up an admin account for UI use

Existing demo credentials are deliberately not printed or saved. To use the admin screens:

1. In the UI, create your own account (it starts as a patient), then sign in.
2. Open Account & security > Set up authenticator.
3. Add the displayed private setup key to your authenticator app as a time-based (TOTP)
   account, then submit its current six-digit code. Do not share the setup key.
4. In your local project terminal, promote YOUR registered email:

   ```powershell
   docker compose exec api python -m app.manage promote-admin --email YOUR_REGISTERED_EMAIL
   ```

5. Sign in again using your password and the next unused authenticator code.
6. The Admin workspace appears in the navigation.

Admin access is intentionally a trusted operator action; public users cannot select their role.

## Add a doctor and publish a bookable slot

1. Register a separate doctor account in the UI, sign in, and enable its MFA.
2. Copy its user ID from Account & security. Sign out.
3. Sign in as admin with a fresh MFA code.
4. Admin workspace > Welcome a doctor: paste the doctor's user ID, enter specialty and fee
   in rupees, then create its doctor profile.
5. Sign out; sign in as that doctor with its password and fresh MFA code.
6. Open Availability, choose future start/end times, and Publish availability.
7. Sign out; sign in as a patient, find the doctor, and book that slot.

To finish a consultation, sign in as the assigned doctor, open Consultations > View details,
start the consultation, save a prescription, then complete it. The patient can read it in
My appointments. Only the assigned doctor can issue the prescription. Admins see analytics
and audit metadata, without clinical access.

## Notes

- Responsive HTML/CSS/JavaScript; same-origin API calls to your existing backend.
- No passwords/tokens saved in localStorage or sessionStorage; the token is in tab memory.
- Domain mutation requests carry an automatic UUID idempotency key, retained for one bounded
  retry on network/502/503/504 failures. Login is not automatically retried because OTPs are single-use.
- Auth rate limits apply to registration/login/MFA: if you reach 429, wait a minute.
- Timestamps are shown in your device timezone and saved with UTC offsets.
- Payments remain a local pending/cancelled ledger; no money is collected.
- The frontend has no video-call implementation, password recovery, prescription editing or
  account deletion, because those workflows are not implemented by this backend.
- Optional developer DOM tests: Node 24+, `npm ci --ignore-scripts`, then `npm run test:ui`.
  Node/npm is needed only for those optional tests, not for Docker runtime.
