"use client";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ClientsTable } from "./ClientsTable";
import { ConsultantsTable } from "./ConsultantsTable";
import { PlacementsTable } from "./PlacementsTable";
import { ProjectsTable } from "./ProjectsTable";

/** The placement register: placements first, then the records they hang off. */
export function RegisterTab() {
  return (
    <Tabs defaultValue="placements" className="space-y-3">
      <TabsList>
        <TabsTrigger value="placements">Placements</TabsTrigger>
        <TabsTrigger value="consultants">Consultants</TabsTrigger>
        <TabsTrigger value="clients">Clients</TabsTrigger>
        <TabsTrigger value="projects">Projects</TabsTrigger>
      </TabsList>
      <TabsContent value="placements">
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
