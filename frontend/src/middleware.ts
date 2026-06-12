import { clerkMiddleware, createRouteMatcher } from "@clerk/nextjs/server";

// Rutas que exigen sesión. /dashboard (y lo que cuelgue) queda protegido;
// el resto (landing, sign-in modal) es público.
const isProtected = createRouteMatcher(["/dashboard(.*)"]);

export default clerkMiddleware(async (auth, req) => {
  if (isProtected(req)) {
    await auth.protect();
  }
});

export const config = {
  matcher: [
    // Todo menos assets estáticos y _next.
    "/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)",
    "/(api|trpc)(.*)",
  ],
};
