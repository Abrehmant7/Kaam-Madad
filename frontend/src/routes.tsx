import type { RouteObject } from "react-router";

import { GuestOnly, RequireAuth } from "./auth/guards";
import { AppShell } from "./components/layout/AppShell";
import { CatalogPreviewPage } from "./pages/CatalogPreviewPage";
import { BookingPage } from "./pages/BookingPage";
import { ChatStage, ConversationRoute, QuoteStage } from "./pages/ConversationPage";
import { DiagnosticsPage } from "./pages/DiagnosticsPage";
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
import { WorkerProfilePage } from "./pages/worker/WorkerProfilePage";

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
          { index: true, element: <LandingPage /> },
          { path: "start", element: <StartPage /> },
          { path: "signup", element: <SignupPage /> },
          { path: "login", element: <LoginPage /> },
        ],
      },
      { path: "catalog", element: <CatalogPreviewPage /> },
      // Developer diagnostics (server readiness): reachable by URL only, never from the normal navigation.
      { path: "diagnostics", element: <DiagnosticsPage /> },
      {
        element: <RequireAuth />,
        children: [
          { path: "account", element: <AccountHomePage /> },
          { path: "account/phone", element: <PhoneConfirmationPage /> },
          // Developer tools: not linked from the normal navigation.
          { path: "voice-test", element: <VoiceTestPage /> },
          // A job's stages: Request & chat → Quote (same invitation) → Work progress (the booking).
          {
            path: "conversations/:id",
            element: <ConversationRoute />,
            children: [
              { index: true, element: <ChatStage />, handle: { stage: "chat" } },
              { path: "quote", element: <QuoteStage />, handle: { stage: "quote" } },
            ],
          },
          { path: "bookings/:id", element: <BookingPage /> },
          { path: "reports", element: <ReportsPage /> },
          { path: "reports/new", element: <ReportNewPage /> },
          { path: "reports/:id", element: <ReportDetailPage /> },
        ],
      },
      {
        path: "worker",
        element: <RequireAuth role="worker" />,
        children: [
          { index: true, element: <WorkerDashboardPage /> },
          { path: "profile", element: <WorkerProfilePage /> },
          { path: "setup/work", element: <OnboardingWorkPage /> },
          { path: "setup/areas", element: <OnboardingAreasPage /> },
          // Event demo flow: two sample uploads. The M4 card scan + demo registry stays available, outside the default flow.
          { path: "verify", element: <DemoVerifyPage /> },
          { path: "verify/card", element: <VerifyIdentityPage /> },
          { path: "invitations/:id", element: <WorkerInvitationPage /> },
        ],
      },
      {
        path: "customer",
        element: <RequireAuth role="customer" />,
        children: [
          { index: true, element: <CustomerDashboardPage /> },
          { path: "requests/new", element: <DescribeJobPage /> },
          { path: "requests/:id", element: <JobDetailPage /> },
          { path: "requests/:id/details", element: <JobDetailsPage /> },
          { path: "requests/:id/review", element: <JobReviewPage /> },
          { path: "requests/:id/workers", element: <FindWorkersPage /> },
        ],
      },
      { path: "*", element: <NotFoundPage /> },
    ],
  },
];
