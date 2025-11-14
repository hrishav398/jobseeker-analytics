"use client";
import { useEffect, useState } from "react";
import { Card, CardBody, CardHeader, Spinner } from "@heroui/react";

interface DashboardMetrics {
	total_applications: number;
	interview_rate: number;
	offer_rate: number;
	avg_time_to_response: number;
	applications_last_7_days: number;
	applications_last_30_days: number;
	active_applications: number;
	applications_by_status: Record<string, number>;
	applications_per_week: { week: string; count: number }[];
	applications_per_month: { month: string; count: number }[];
}

interface MetricCardProps {
	title: string;
	value: string | number;
	subtitle?: string;
	color?: string;
}

function MetricCard({ title, value, subtitle, color = "blue" }: MetricCardProps) {
	const colorClasses = {
		blue: "bg-blue-50 dark:bg-blue-900/20 border-blue-200 dark:border-blue-800",
		green: "bg-green-50 dark:bg-green-900/20 border-green-200 dark:border-green-800",
		orange: "bg-orange-50 dark:bg-orange-900/20 border-orange-200 dark:border-orange-800",
		purple: "bg-purple-50 dark:bg-purple-900/20 border-purple-200 dark:border-purple-800",
		gray: "bg-gray-50 dark:bg-gray-900/20 border-gray-200 dark:border-gray-800"
	};

	const textColorClasses = {
		blue: "text-blue-600 dark:text-blue-400",
		green: "text-green-600 dark:text-green-400",
		orange: "text-orange-600 dark:text-orange-400",
		purple: "text-purple-600 dark:text-purple-400",
		gray: "text-gray-600 dark:text-gray-400"
	};

	return (
		<Card className={`${colorClasses[color as keyof typeof colorClasses]} border-2`}>
			<CardBody className="p-4">
				<p className="text-sm text-gray-600 dark:text-gray-400 mb-1">{title}</p>
				<p className={`text-3xl font-bold ${textColorClasses[color as keyof typeof textColorClasses]}`}>
					{value}
				</p>
				{subtitle && <p className="text-xs text-gray-500 dark:text-gray-500 mt-1">{subtitle}</p>}
			</CardBody>
		</Card>
	);
}

export default function DashboardMetrics() {
	const [metrics, setMetrics] = useState<DashboardMetrics | null>(null);
	const [loading, setLoading] = useState(true);
	const [error, setError] = useState<string | null>(null);

	const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

	useEffect(() => {
		const fetchMetrics = async () => {
			try {
				setLoading(true);
				const response = await fetch(`${apiUrl}/dashboard-metrics`, {
					method: "GET",
					credentials: "include"
				});

				if (!response.ok) {
					throw new Error("Failed to fetch metrics");
				}

				const data = await response.json();
				setMetrics(data);
			} catch (err) {
				setError("Failed to load metrics");
				console.error(err);
			} finally {
				setLoading(false);
			}
		};

		fetchMetrics();
	}, [apiUrl]);

	if (loading) {
		return (
			<div className="flex justify-center items-center p-8">
				<Spinner size="lg" />
			</div>
		);
	}

	if (error || !metrics) {
		return (
			<div className="p-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg">
				<p className="text-red-600 dark:text-red-400">{error || "No metrics available"}</p>
			</div>
		);
	}

	return (
		<div className="space-y-6">
			{/* Key Metrics Grid */}
			<div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
				<MetricCard
					color="blue"
					title="Total Applications"
					value={metrics.total_applications}
				/>
				<MetricCard
					color="green"
					title="Interview Rate"
					subtitle="% that led to interviews"
					value={`${metrics.interview_rate}%`}
				/>
				<MetricCard
					color="purple"
					title="Offer Rate"
					subtitle="% that led to offers"
					value={`${metrics.offer_rate}%`}
				/>
				<MetricCard
					color="orange"
					title="Active Applications"
					subtitle="Still in progress"
					value={metrics.active_applications}
				/>
			</div>

			{/* Time-based Metrics */}
			<div className="grid grid-cols-1 md:grid-cols-3 gap-4">
				<MetricCard
					color="blue"
					title="Last 7 Days"
					value={metrics.applications_last_7_days}
				/>
				<MetricCard
					color="blue"
					title="Last 30 Days"
					value={metrics.applications_last_30_days}
				/>
				<MetricCard
					color="gray"
					title="Avg. Time to Response"
					subtitle="Days until response"
					value={metrics.avg_time_to_response > 0 ? `${metrics.avg_time_to_response} days` : "N/A"}
				/>
			</div>

			{/* Status Breakdown */}
			<Card className="bg-white dark:bg-gray-800">
				<CardHeader className="pb-2">
					<h3 className="text-lg font-semibold text-gray-800 dark:text-gray-200">
						Applications by Status
					</h3>
				</CardHeader>
				<CardBody>
					<div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
						{Object.entries(metrics.applications_by_status)
							.sort((a, b) => b[1] - a[1])
							.map(([status, count]) => (
								<div
									key={status}
									className="flex justify-between items-center p-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg"
								>
									<span className="text-sm text-gray-700 dark:text-gray-300">{status}</span>
									<span className="font-semibold text-gray-900 dark:text-gray-100">{count}</span>
								</div>
							))}
					</div>
				</CardBody>
			</Card>
		</div>
	);
}
