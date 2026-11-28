import type { RouteObject } from "react-router";

import { GuestOnly, RequireAuth } from "./auth/guards";
import { AppShell } from "./components/layout/AppShell";
import { CatalogPreviewPage } from "./pages/CatalogPreviewPage";
import { BookingPage } from "./pages/BookingPage";
import { ConversationPage } from "./pages/ConversationPage";
import { ReportNewPage } from "./pages/ReportNewPage";
import { ReportDetailPage, ReportsPage } from "./pages/ReportsPages";
import { CustomerDashboardPage } from "./pages/customer/CustomerDashboardPage";
import { DescribeJobPage } from "./pages/customer/DescribeJobPage";
import { FindWorkersPage } from "./pages/customer/FindWorkersPage";
import { JobDetailPage } from "./pages/customer/JobDetailPage";
import { JobDetailsPage } from "./pages/customer/JobDetailsPage";
import { JobReviewPage } from "./pages/customer/JobReviewPage";
import { AccountHomePage } from "./pages/HomePages";
import { LandingPage } from "./pages/LandingPage";
import { LoginPage } from "./pages/LoginPage";
import { NotFoundPage } from "./pages/NotFoundPage";
import { PhoneConfirmationPage } from "./pages/PhoneConfirmationPage";
import { RouteErrorPage } from "./pages/RouteErrorPage";
import { SignupPage } from "./pages/SignupPage";
import { VoiceTestPage } from "./pages/VoiceTestPage";
import { StartPage } from "./pages/StartPage";
import { DemoVerifyPage } from "./pages/worker/DemoVerifyPage";
import { OnboardingAreasPage } from "./pages/worker/OnboardingAreasPage";
import { OnboardingWorkPage } from "./pages/worker/OnboardingWorkPage";
import { VerifyIdentityPage } from "./pages/worker/VerifyIdentityPage";
import { WorkerInvitationPage } from "./pages/worker/WorkerInvitationPage";
import { WorkerDashboardPage } from "./pages/worker/WorkerDashboardPage";

// Feature modules add their routes here (worker onboarding, requests, bookings…).
export const routes: RouteObject[] = [
  {
    path: "/",
    element: <AppShell />,
    errorElement: <RouteErrorPage />,
    children: [
      {
        element: <GuestOnly />,
        children: [
          { index: true, element: <LandingPage />, handle: { width: "wide" } },
          { path: "start", element: <StartPage /> },
          { path: "signup", element: <SignupPage /> },
          { path: "login", element: <LoginPage /> },
        ],
      },
      { path: "catalog", element: <CatalogPreviewPage />, handle: { width: "medium" } },
      {
        element: <RequireAuth />,
        children: [
          { path: "account", element: <AccountHomePage /> },
          { path: "account/phone", element: <PhoneConfirmationPage /> },
          { path: "voice-test", element: <VoiceTestPage /> },
          // Chat beside the quote terms on desktop.
          { path: "conversations/:id", element: <ConversationPage />, handle: { width: "wide" } },
          { path: "bookings/:id", element: <BookingPage />, handle: { width: "medium" } },
          { path: "reports", element: <ReportsPage /> },
          { path: "reports/new", element: <ReportNewPage /> },
          { path: "reports/:id", element: <ReportDetailPage /> },
        ],
      },
      {
        path: "worker",
        element: <RequireAuth role="worker" />,
        children: [
          { index: true, element: <WorkerDashboardPage />, handle: { width: "wide" } },
          // "Answer by voice" sits beside the manual choices on desktop.
          { path: "setup/work", element: <OnboardingWorkPage />, handle: { width: "medium" } },
          { path: "setup/areas", element: <OnboardingAreasPage />, handle: { width: "medium" } },
          // Event demo flow: two sample uploads. The M4 card scan + demo registry stays available, outside the default flow.
          { path: "verify", element: <DemoVerifyPage /> },
          { path: "verify/card", element: <VerifyIdentityPage /> },
          { path: "invitations/:id", element: <WorkerInvitationPage />, handle: { width: "medium" } },
        ],
      },
      {
        path: "customer",
        element: <RequireAuth role="customer" />,
        children: [
          { index: true, element: <CustomerDashboardPage />, handle: { width: "wide" } },
          { path: "requests/new", element: <DescribeJobPage /> },
          { path: "requests/:id", element: <JobDetailPage /> },
          { path: "requests/:id/details", element: <JobDetailsPage /> },
          { path: "requests/:id/review", element: <JobReviewPage /> },
          { path: "requests/:id/workers", element: <FindWorkersPage />, handle: { width: "medium" } },
        ],
      },
      { path: "*", element: <NotFoundPage /> },
    ],
  },
];
