import { redirect } from "next/navigation";

export default function AnalysesRedirect() {
  redirect("/tweets?tab=analyzed");
}
