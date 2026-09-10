package io.cybersaarthi.fieldagent.ui.navigation

import androidx.compose.runtime.Composable
import androidx.navigation.NavHostController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import io.cybersaarthi.fieldagent.ui.screen.auth.LoginScreen
import io.cybersaarthi.fieldagent.ui.screen.dashboard.DashboardScreen
import io.cybersaarthi.fieldagent.ui.screen.case_detail.CaseDetailScreen
import io.cybersaarthi.fieldagent.ui.screen.collection.CollectionCaptureScreen

object Routes {
    const val LOGIN = "login"
    const val DASHBOARD = "dashboard"
    const val CASE_DETAIL_PATTERN = "case/{caseId}"
    const val COLLECTION_CAPTURE_PATTERN = "case/{caseId}/collection/{collectionId}/capture"

    fun caseDetail(caseId: String) = "case/$caseId"
    fun collectionCapture(caseId: String, collectionId: String) =
        "case/$caseId/collection/$collectionId/capture"
}

@Composable
fun NavGraph(navController: NavHostController = rememberNavController()) {
    NavHost(navController = navController, startDestination = Routes.LOGIN) {
        composable(Routes.LOGIN) {
            LoginScreen(
                onLoginSuccess = {
                    navController.navigate(Routes.DASHBOARD) {
                        popUpTo(Routes.LOGIN) { inclusive = true }
                    }
                }
            )
        }
        composable(Routes.DASHBOARD) {
            DashboardScreen(
                onCaseClick = { caseId -> navController.navigate(Routes.caseDetail(caseId)) },
                onLogout = {
                    navController.navigate(Routes.LOGIN) {
                        popUpTo(Routes.DASHBOARD) { inclusive = true }
                    }
                }
            )
        }
        composable(Routes.CASE_DETAIL_PATTERN) { _ ->
            CaseDetailScreen(
                onCollectionClick = { caseId, collId ->
                    navController.navigate(Routes.collectionCapture(caseId, collId))
                },
                onBack = { navController.popBackStack() }
            )
        }
        composable(Routes.COLLECTION_CAPTURE_PATTERN) { _ ->
            CollectionCaptureScreen(
                onBack = { navController.popBackStack() },
                onComplete = { navController.popBackStack() }
            )
        }
    }
}