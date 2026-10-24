import { useQuery } from "@tanstack/react-query";
import { isStaticMode } from "./mode";
import { getManifest, type Manifest } from "./static";

/** The published snapshot's manifest: when the data was last verified and when the site was built from it. */
export const useSnapshot = () =>
  useQuery<Manifest>({
    queryKey: ["snapshot-manifest"],
    queryFn: ({ signal }) => getManifest(signal),
    enabled: isStaticMode(),
    staleTime: Infinity,
  });
