import { FileSearch, Gauge, History, Radar, ScrollText } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'

import { ActionBar } from '@/console/components/case/ActionBar'
import { AuditTab } from '@/console/components/case/AuditTab'
import { CaseHeader } from '@/console/components/case/CaseHeader'
import { EvidenceTab } from '@/console/components/case/EvidenceTab'
import { IntelTab } from '@/console/components/case/IntelTab'
import { RiskTab } from '@/console/components/case/RiskTab'
import { SummaryTab } from '@/console/components/case/SummaryTab'
import { analystFlags } from '@/console/evidence'
import { useCase } from '@/console/useCase'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'

const Count = ({ n }: { n: number }) =>
  n > 0 ? <span className="rounded-full bg-muted px-1.5 text-xs font-semibold tabular-nums text-foreground">{n}</span> : null

// The case view (UI_SPEC Area 2, item 2): header, five tabs, and the sticky action bar.
export function CaseView({ caseId }: { caseId: string }) {
  const { load, reload } = useCase(caseId)
  const [tab, setTab] = useState('summary')

  if (load.status === 'loading') {
    return (
      <div className="flex flex-col gap-4 p-6" aria-busy="true" aria-label="Loading the case">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-6 w-2/3" />
        <Skeleton className="h-10 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    )
  }
  if (load.status === 'error') {
    return (
      <div className="flex flex-col items-start gap-3 p-6">
        <h2 className="text-lg font-semibold">{load.notFound ? 'Case not found' : 'This case couldn’t be loaded'}</h2>
        <p className="text-sm text-muted-foreground">
          {load.notFound ? 'It may have been cleared by a demo reset.' : 'Check your connection and try again.'}
        </p>
        <Link to="/console" className="text-sm font-medium text-primary underline underline-offset-4">
          Back to the queue
        </Link>
      </div>
    )
  }

  const { detail } = load
  const intelCount = (detail.intel?.watchlist_matches.length ?? 0) + (detail.intel?.web_findings.length ?? 0)
  return (
    <div className="flex h-full min-h-0 flex-col" data-testid="case-view">
      <div className="min-h-0 flex-1 overflow-y-auto">
        <CaseHeader detail={detail} />
        <Tabs value={tab} onValueChange={setTab} className="px-4 pt-2 pb-6 sm:px-6">
          <TabsList aria-label="Case details">
            <TabsTrigger value="summary">
              <ScrollText aria-hidden="true" /> Summary
            </TabsTrigger>
            <TabsTrigger value="evidence">
              <FileSearch aria-hidden="true" /> Evidence <Count n={analystFlags(detail).length} />
            </TabsTrigger>
            <TabsTrigger value="risk">
              <Gauge aria-hidden="true" /> Transaction risk
            </TabsTrigger>
            <TabsTrigger value="intel">
              <Radar aria-hidden="true" /> Intel <Count n={intelCount} />
            </TabsTrigger>
            <TabsTrigger value="audit">
              <History aria-hidden="true" /> Audit <Count n={detail.audit.length} />
            </TabsTrigger>
          </TabsList>
          <TabsContent value="summary" className="pt-4">
            <SummaryTab detail={detail} />
          </TabsContent>
          <TabsContent value="evidence" className="pt-4">
            <EvidenceTab detail={detail} />
          </TabsContent>
          <TabsContent value="risk" className="pt-4">
            <RiskTab detail={detail} />
          </TabsContent>
          <TabsContent value="intel" className="pt-4">
            <IntelTab detail={detail} />
          </TabsContent>
          <TabsContent value="audit" className="pt-4">
            <AuditTab detail={detail} />
          </TabsContent>
        </Tabs>
      </div>
      <ActionBar detail={detail} onDecided={() => void reload()} />
    </div>
  )
}
