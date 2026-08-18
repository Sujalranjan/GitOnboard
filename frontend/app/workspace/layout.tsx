/**
 * Root workspace layout — suppresses the root layout's Header
 * since WorkspaceLayout has its own HeaderGlobal.
 */
export default function RootWorkspaceLayout({
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
