/**
 * Workspace layout — suppresses the parent repository layout's Sidebar
 * and root layout's Header since WorkspaceLayout has its own HeaderGlobal.
 */
export default function WorkspaceRouteLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="fixed inset-0 z-50 bg-[#0A0D10]">
      {children}
    </div>
  );
}
