"use client";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

const SUB_TAB =
  "flex-none rounded-md px-3 data-[state=active]:border-transparent data-[state=active]:bg-primary data-[state=active]:text-primary-foreground data-[state=active]:shadow-none dark:data-[state=active]:border-transparent dark:data-[state=active]:bg-primary dark:data-[state=active]:text-primary-foreground";
import { ClientsTable } from "./ClientsTable";
import { ConsultantsTable } from "./ConsultantsTable";
import { PlacementsTable } from "./PlacementsTable";
import { QuickAddCard } from "./QuickAddCard";
import { ProjectsTable } from "./ProjectsTable";

/** The placement register: placements first, then the records they hang off. */
export function RegisterTab() {
  return (
    <Tabs defaultValue="placements" className="space-y-3">
      <TabsList className="gap-1 bg-transparent p-0">
        <TabsTrigger value="placements" className={SUB_TAB}>
          Placements
        </TabsTrigger>
        <TabsTrigger value="consultants" className={SUB_TAB}>
          Consultants
        </TabsTrigger>
        <TabsTrigger value="clients" className={SUB_TAB}>
          Clients
        </TabsTrigger>
        <TabsTrigger value="projects" className={SUB_TAB}>
          Projects
        </TabsTrigger>
      </TabsList>
      <TabsContent value="placements" className="space-y-4">
        <QuickAddCard />
        <PlacementsTable />
      </TabsContent>
      <TabsContent value="consultants">
        <ConsultantsTable />
      </TabsContent>
      <TabsContent value="clients">
        <ClientsTable />
      </TabsContent>
      <TabsContent value="projects">
        <ProjectsTable />
      </TabsContent>
    </Tabs>
  );
}
