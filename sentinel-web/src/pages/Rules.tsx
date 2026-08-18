import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, Trash2, RefreshCw, FileText } from 'lucide-react'
import axios from 'axios'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

interface RuleSummary {
  id: string
  title: string
  level: string
  file_path: string
}

export default function Rules() {
  const queryClient = useQueryClient()
  const [showCreateModal, setShowCreateModal] = useState(false)

  const { data, isLoading, error } = useQuery({
    queryKey: ['rules'],
    queryFn: async () => {
      const response = await axios.get(`${API_URL}/api/v1/rules`)
      return response.data
    },
  })

  const deleteMutation = useMutation({
    mutationFn: async (ruleId: string) => {
      await axios.delete(`${API_URL}/api/v1/rules/${ruleId}`)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['rules'] })
    },
  })

  const reloadMutation = useMutation({
    mutationFn: async () => {
      await axios.post(`${API_URL}/api/v1/rules/reload`)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['rules'] })
    },
  })

  const getLevelColor = (level: string) => {
    switch (level) {
      case 'critical':
        return 'bg-red-500/20 text-red-400'
      case 'high':
        return 'bg-orange-500/20 text-orange-400'
      case 'medium':
        return 'bg-yellow-500/20 text-yellow-400'
      case 'low':
        return 'bg-blue-500/20 text-blue-400'
      default:
        return 'bg-gray-500/20 text-gray-400'
    }
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-gray-400">Loading rules...</div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="bg-red-500/10 border border-red-500 rounded-lg p-4">
        <p className="text-red-400">Failed to load rules</p>
      </div>
    )
  }

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-3xl font-bold mb-2">Sigma Rules</h2>
          <p className="text-gray-400">
            {data?.total || 0} detection rules
          </p>
        </div>
        <div className="flex space-x-3">
          <button
            onClick={() => reloadMutation.mutate()}
            disabled={reloadMutation.isPending}
            className="flex items-center space-x-2 px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg transition-colors"
          >
            <RefreshCw className={`w-4 h-4 ${reloadMutation.isPending ? 'animate-spin' : ''}`} />
            <span>Reload</span>
          </button>
          <button
            onClick={() => setShowCreateModal(true)}
            className="flex items-center space-x-2 px-4 py-2 bg-primary-600 hover:bg-primary-700 rounded-lg transition-colors"
          >
            <Plus className="w-4 h-4" />
            <span>New Rule</span>
          </button>
        </div>
      </div>

      {/* Rules list */}
      <div className="bg-gray-800 rounded-lg border border-gray-700">
        {data?.rules && data.rules.length > 0 ? (
          <div className="divide-y divide-gray-700">
            {data.rules.map((rule: RuleSummary) => (
              <div key={rule.id} className="p-4 hover:bg-gray-700/50 transition-colors">
                <div className="flex items-center justify-between">
                  <div className="flex items-start space-x-3 flex-1">
                    <FileText className="w-5 h-5 text-gray-400 mt-0.5" />
                    <div className="flex-1">
                      <div className="flex items-center space-x-3 mb-1">
                        <h3 className="font-medium">{rule.title}</h3>
                        <span className={`px-2 py-0.5 rounded text-xs font-medium ${getLevelColor(rule.level)}`}>
                          {rule.level}
                        </span>
                      </div>
                      <p className="text-sm text-gray-400">ID: {rule.id}</p>
                      <p className="text-sm text-gray-500">{rule.file_path}</p>
                    </div>
                  </div>
                  <div className="flex items-center space-x-2">
                    <button
                      onClick={() => {
                        if (confirm(`Delete rule ${rule.id}?`)) {
                          deleteMutation.mutate(rule.id)
                        }
                      }}
                      disabled={deleteMutation.isPending}
                      className="p-2 text-red-400 hover:bg-red-500/10 rounded transition-colors"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="p-12 text-center text-gray-400">
            <FileText className="w-12 h-12 mx-auto mb-4 text-gray-600" />
            <p>No rules found</p>
          </div>
        )}
      </div>

      {/* Create modal - placeholder for now */}
      {showCreateModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-gray-800 rounded-lg p-6 max-w-2xl w-full mx-4">
            <h3 className="text-xl font-bold mb-4">Create New Rule</h3>
            <p className="text-gray-400 mb-4">
              Rule creation UI coming soon. For now, add rules manually to the rules/ directory.
            </p>
            <button
              onClick={() => setShowCreateModal(false)}
              className="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg transition-colors"
            >
              Close
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
