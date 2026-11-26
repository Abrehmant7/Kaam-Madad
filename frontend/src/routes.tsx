import type { RouteObject } from "react-router";

import { GuestOnly, RequireAuth } from "./auth/guards";
import { AppShell } from "./components/layout/AppShell";
import { CatalogPreviewPage } from "./pages/CatalogPreviewPage";
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
          { index: true, element: <LandingPage /> },
          { path: "start", element: <StartPage /> },
          { path: "signup", element: <SignupPage /> },
          { path: "login", element: <LoginPage /> },
        ],
      },
      { path: "catalog", element: <CatalogPreviewPage /> },
      {
        element: <RequireAuth />,
        children: [
          { path: "account", element: <AccountHomePage /> },
          { path: "account/phone", element: <PhoneConfirmationPage /> },
          { path: "voice-test", element: <VoiceTestPage /> },
        ],
      },
      {
        path: "worker",
        element: <RequireAuth role="worker" />,
        children: [
          { index: true, element: <WorkerDashboardPage /> },
          { path: "setup/work", element: <OnboardingWorkPage /> },
          { path: "setup/areas", element: <OnboardingAreasPage /> },
          { path: "verify", element: <VerifyIdentityPage /> },
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
