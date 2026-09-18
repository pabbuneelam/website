export function formatSalary(dollars: number | null): string {
  if (dollars === null) return '—'
  return `$${(dollars / 1_000_000).toFixed(1)}M`
}

export function formatValuePerMillion(ovr: number, contract: number): string {
  if (!contract) return '—'
  return (ovr / (contract / 1_000_000)).toFixed(2)
}
