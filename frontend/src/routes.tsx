import type { RouteObject } from "react-router";

import { GuestOnly, RequireAuth } from "./auth/guards";
import { AppShell } from "./components/layout/AppShell";
import { CatalogPreviewPage } from "./pages/CatalogPreviewPage";
import { AccountHomePage, CustomerHomePage } from "./pages/HomePages";
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
        ],
      },
      { path: "customer", element: <RequireAuth role="customer"><CustomerHomePage /></RequireAuth> },
      { path: "*", element: <NotFoundPage /> },
    ],
  },
];
