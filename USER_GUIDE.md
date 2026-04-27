# PyCashFlow User Guide

## 1. Introduction

Welcome to **PyCashFlow**. This guide explains how to use the app as an:

- **Account Owner** (full access to manage shared financial data)
- **Guest User** (read-only access to an Account Owner’s shared data)

PyCashFlow is available in two user-facing modes:

- **PyCashFlow Cloud**: hosted service with subscription-based access.
- **Self-hosted mode**: connected to your own PyCashFlow server.

This guide focuses on everyday usage in the web app and iOS app.

---

## 2. Getting Started

### 2.1 Choose your mode

When you use the iOS app, you can choose:

- **PyCashFlow Cloud**
- **Self-Hosted**

If you use the web app directly in a browser, you are already connected to that web server.

### 2.2 First-time setup paths

You can become an **Account Owner** in either of these ways:

1. **Web sign-up path**
   - Open the web app.
   - Select **Create Account**.
   - Enter your email, name, and password.
   - Sign in after your account is available.

2. **PyCashFlow Cloud subscription path (iOS App Store)**
   - Open the iOS app in **PyCashFlow Cloud** mode.
   - Go to **Activate or Restore Cloud Subscription**.
   - Enter the email for your cloud account.
   - Complete purchase (or restore).
   - If this email is new, you receive a one-time setup email to create your password.
   - Then sign in with that email and password.

### 2.3 Sign in options

Depending on what is enabled for your account/server, sign-in can include:

- Email + password
- 2FA verification code (or backup code)
- Passkey sign-in

### 2.4 Password reset

If you forget your password in the web app:

1. Select **Forgot password**.
2. Enter your email.
3. Use the one-time link sent to your email.
4. Set your new password.

---

## 3. Account Owners

As an **Account Owner**, you can fully manage the shared financial workspace.

### 3.1 What Account Owners can do

- Add, edit, and delete recurring schedules (income/expenses)
- Add and edit scenario items for what-if planning
- Add and remove holds/skips
- Update current balance
- Review transaction projections and risk indicators
- Configure AI insights and refresh insights
- Import/export schedule data (web)
- Invite, activate/deactivate, and remove Guest Users
- Update your profile and password
- Enable/disable 2FA
- Manage passkeys
- Delete your account (web)

### 3.2 Account creation

You can start as an Account Owner via:

- Web sign-up (Create Account), or
- PyCashFlow Cloud App Store activation with email-based setup.

### 3.3 Managing your financial data

Typical owner workflow:

1. Set a current balance.
2. Add recurring income and expense schedules.
3. Add scenario items for optional what-if changes.
4. Add holds/skips as needed.
5. Review dashboard projection and upcoming transactions.
6. Adjust schedules/scenarios as your plans change.

### 3.4 Managing Guest Users

From the web app Guest Management page, Account Owners can:

- Invite a Guest User by name and email
- Send a one-time password setup email automatically
- Deactivate/reactivate guest access
- Remove a guest from shared access

---

## 4. Guest Users

A **Guest User** is a read-only user invited by an Account Owner.

### 4.1 How invitation works

1. Account Owner adds guest name and email.
2. Guest receives a one-time setup email.
3. Guest sets password and signs in.

### 4.2 What Guest Users can access

Guest Users can view shared owner data, including:

- Dashboard metrics
- Projections/charts
- Upcoming transactions
- Cached AI insight results

### 4.3 Guest User limitations

Guest Users cannot make owner-level data changes, including:

- Creating/updating/deleting schedules
- Creating/updating/deleting scenarios
- Setting balance
- Creating/deleting holds or skips
- Refreshing AI insights
- Purchasing owner activation

Guest Users can still manage their own sign-in credentials/settings available to users (such as password/profile updates where offered).

### 4.4 Shared-data behavior

Guest Users see the Account Owner’s shared financial dataset and projections.

When owner access is no longer active in PyCashFlow Cloud, guest access is also affected until owner access is active again.

---

## 5. Using PyCashFlow (Web App)

### 5.1 Main navigation

For Account Owners, top navigation includes:

- Dashboard
- Schedule
- Scenarios
- Transactions
- Holds
- Settings
- Guests
- Logout

Guest Users see a simplified navigation:

- Dashboard
- Settings
- Logout

### 5.2 Dashboard

The dashboard provides:

- Current balance
- Lowest projected balance (90-day view)
- Cash risk score/status
- Projection chart
- Upcoming transaction list
- AI insights summary (if configured)

Account Owners can update balance from dashboard controls.

### 5.3 Schedule management (Account Owner)

In **Schedule**:

- Add recurring income/expense items
- Choose type, amount, frequency, and start date
- Edit existing items
- Delete items
- Add holds directly from schedule items
- Export and import schedule data

### 5.4 Scenario planning (Account Owner)

In **Scenarios**:

- Add optional what-if items
- Edit or remove scenario items
- Compare projected effects in dashboard/chart views

### 5.5 Holds and skips (Account Owner)

In **Holds**:

- View active holds and skips
- Remove individual holds/skips
- Clear all holds or all skips

From schedules/transactions, you can add a hold or skip.

### 5.6 Transactions view

The **Transactions** page shows projected upcoming transactions generated from your current balance and recurring items.

### 5.7 Settings

User-level settings include:

- Account profile updates (name/email/password)
- 2FA setup/disable
- Passkey management
- AI settings (owners)
- Email integration settings (owners, where available)
- About/version information
- Account deletion (Account Owner self-service)

### 5.8 Passkeys

If passkeys are available on your server/browser:

- You can register one or more passkeys
- Use passkey sign-in from login
- Remove passkeys from settings

### 5.9 2FA (two-factor authentication)

Owners and guests can enable 2FA by:

1. Scanning QR code in authenticator app
2. Entering the 6-digit code
3. Saving backup codes shown one time

At sign-in, use either:

- Authenticator code, or
- A backup code

### 5.10 Offline behavior (web)

The web app does not cache authenticated HTML pages for offline viewing.

- If your connection drops while navigating pages, the app shows an offline banner/page.
- Some static assets (for example CSS, icons, and offline page resources) are cached to help the app shell load.
- Logging out clears cached page data for privacy.

---

## 6. Using PyCashFlow (iOS App)

### 6.1 Login and account mode

On the login screen, choose:

- **PyCashFlow Cloud** or
- **Self-Hosted**

Then sign in with email/password, passkey, or (if prompted) 2FA code.

### 6.2 Connecting to a self-hosted server

In **Self-Hosted** mode:

1. Enter your server API URL.
2. Save it.
3. Sign in normally.

For local testing, localhost-style HTTP addresses can be used. For remote servers, use secure URLs.

### 6.3 Cloud activation and restore (App Store)

In **PyCashFlow Cloud** mode:

1. Open **Activate or Restore Cloud Subscription**.
2. Enter your cloud account email.
3. Choose a subscription product and complete purchase, or use **Restore Purchases**.
4. After verification, sign in (or complete emailed password setup if this is a new account email).

### 6.4 What you can do in iOS

Account Owner features in iOS include:

- Dashboard overview with chart and upcoming transactions
- Balance updates and balance history
- Add/edit/delete schedules
- Add schedule hold/skip actions
- Add/edit/delete scenarios
- View/remove holds and skips
- View and refresh AI insights
- Open settings, change password, refresh subscription status, logout

Guest User behavior in iOS:

- Read-oriented dashboard access
- Settings access
- No owner-level data write actions

### 6.5 iOS navigation differences

- Account Owners see a bottom floating navigation bar to major features.
- On smaller screens, if all nav buttons are not visible at once, swipe the bar horizontally to reveal additional buttons.
- Guest Users get a simplified navigation path focused on dashboard + settings.

### 6.6 Switching accounts / logout

To switch accounts on iOS:

1. Open **Settings**.
2. Tap **Logout**.
3. Sign in with another account.

Switching between Cloud and Self-Hosted modes also signs you out so you can reconnect cleanly.

### 6.7 iOS swipe actions on cards (Account Owner)

In list/card views, swipe gestures provide quick actions:

- **Schedules cards**
  - Swipe right: **Edit**
  - Swipe left: **Delete**, **Hold**, **Skip**
- **Scenarios cards**
  - Swipe right: **Edit**
  - Swipe left: **Delete**
- **Holds/Skips cards**
  - Swipe left: **Delete**

---

## 7. Subscription & Billing (User Perspective Only)

### 7.1 When subscription matters

- In **PyCashFlow Cloud**, active owner subscription is required for owner-level access.
- In **Self-hosted mode**, billing enforcement can be different depending on your server setup.

### 7.2 App Store activation flow (Cloud)

- Purchase or restore in iOS paywall.
- Transaction is verified.
- Access status updates to active when valid.

### 7.3 Lifecycle states you may see

You may see status labels such as:

- Active / Trial / Grace period
- Expired / Canceled / Inactive

### 7.4 Expiration and renewal

If owner access expires in Cloud mode:

- Owner sees access restrictions until renewal/restore succeeds.
- Guest User access tied to that owner is also affected.

After renewal or successful restore, access returns.

### 7.5 Checking your status

You can review subscription status details in app settings/paywall screens and refresh subscription status from iOS settings.

---

## 8. Common Workflows

### 8.1 First-time onboarding (Account Owner)

1. Create account (web) **or** activate via iOS App Store flow.
2. Set password (if setup email was sent).
3. Sign in.
4. Add current balance.
5. Add recurring schedules.
6. Review dashboard projection.
7. Optionally add scenarios and AI insights.
8. Invite Guest Users if needed.

### 8.2 Creating an account (web)

1. Go to login page.
2. Select **Create Account**.
3. Enter name, email, password.
4. Sign in after account is available.

### 8.3 Connecting to a self-hosted server (iOS)

1. On login screen, choose **Self-Hosted**.
2. Enter and save server API URL.
3. Sign in with your account.
4. Confirm dashboard loads data.

### 8.4 Activating PyCashFlow Cloud (iOS)

1. Choose **PyCashFlow Cloud** mode.
2. Open subscription screen.
3. Enter cloud account email.
4. Purchase or restore.
5. Sign in (or complete password setup from email first).

### 8.5 Viewing and understanding projections

1. Open dashboard.
2. Review:
   - Current balance
   - Lowest 90-day point
   - Risk indicator
   - Upcoming transactions
3. Use scenarios to compare “what-if” outcomes.

### 8.6 Adding and editing financial data

1. Add schedules (income/expense cadence).
2. Edit values/dates/frequency as life changes.
3. Add scenario items for optional plans.
4. Use holds/skips for temporary changes.
5. Recheck dashboard impact.

### 8.7 Inviting and managing guests (web)

1. Open **Guests**.
2. Add guest name + email.
3. Guest receives setup email.
4. Activate/deactivate as needed.
5. Remove guest when no longer needed.

### 8.8 Handling expiration and renewal

1. If access is blocked, open subscription/paywall area.
2. Renew subscription or restore purchases.
3. Refresh subscription status.
4. Sign out/in if needed.

### 8.9 Logging out and switching accounts

**Web**: Click **Logout**, then sign in with another account.

**iOS**:

1. Open Settings.
2. Tap Logout.
3. Sign in with different account.
4. Optionally switch Cloud vs Self-Hosted mode before signing in.

---

## 9. Troubleshooting (User-Level Only)

### 9.1 I can’t sign in

- Double-check email/password.
- If 2FA is on, enter valid current code.
- Try backup code if authenticator unavailable.
- Use **Forgot password** if needed.

### 9.2 I’m blocked after subscription change

- Open subscription screen and run **Restore Purchases**.
- Refresh subscription status in settings.
- Sign out and sign back in.

### 9.3 Guest User cannot edit anything

That is expected behavior. Guest Users are read-only by design.

### 9.4 I don’t see data I expected

- Confirm you’re signed into the correct account.
- In iOS, confirm correct mode (Cloud vs Self-Hosted) and server URL.
- Refresh the page/view.

### 9.5 Passkey login fails

- Ensure you are using the same domain/environment where the passkey was created.
- Try password + 2FA login, then re-check passkey setup.

### 9.6 No AI insights shown

- Owners may need to configure AI settings first.
- If configured, use **Refresh AI Insights**.
- Guests can view cached results but cannot refresh.

### 9.7 Offline issues in web app

- Reconnect and refresh.
- Cached pages may work offline only if visited previously.

---

## 10. FAQ

### Q1) What is the difference between Account Owner and Guest User?

- **Account Owner**: full control over shared financial data and guest access.
- **Guest User**: read-only access to owner-shared data.

### Q2) Can I use both web and iOS with the same account?

Yes. You can sign into the same account from web and iOS.

### Q3) Can I connect the iOS app to my own server?

Yes. Use **Self-Hosted** mode and save your server API URL.

### Q4) Do I need an App Store subscription in self-hosted mode?

Not necessarily. Subscription purchase flow is specifically for **PyCashFlow Cloud** activation.

### Q5) How do I invite family members or collaborators?

As an Account Owner, use the **Guests** page in the web app to invite them by email.

### Q6) Can guests refresh AI insights?

No. Guests can view shared insight results, but refresh is owner-only.

### Q7) What happens if my subscription expires in Cloud mode?

Owner access is restricted until renewed/restored, and guest access tied to that owner is also affected.

### Q8) How do I fully remove my account?

Account Owners can delete their own account from web settings after confirming credentials.
