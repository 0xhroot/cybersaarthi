package io.cybersaarthi.fieldagent.ui.navigation

import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation.NavGraph.Companion.findStartDestination
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import androidx.navigation.navArgument
import io.cybersaarthi.fieldagent.data.auth.AuthState
import io.cybersaarthi.fieldagent.di.LocalAppContainer
import io.cybersaarthi.fieldagent.ui.capture.CameraCaptureScreen
import io.cybersaarthi.fieldagent.ui.capture.CameraMode
import io.cybersaarthi.fieldagent.ui.screen.auth.EnrollScreen
import io.cybersaarthi.fieldagent.ui.screen.auth.LoginScreen
import io.cybersaarthi.fieldagent.ui.screen.case_detail.CaseDetailScreen
import io.cybersaarthi.fieldagent.ui.screen.collection.CollectionScreen
import io.cybersaarthi.fieldagent.ui.screen.dashboard.DashboardScreen
import io.cybersaarthi.fieldagent.ui.screen.profile.ProfileScreen

/** Single graph; the start destination reflects whether a valid session exists. */
@Composable
fun CyberSaarthiNavHost() {
    val container = LocalAppContainer.current
    val navController = rememberNavController()
    val session by container.session.state.collectAsStateWithLifecycle()
    val start = when (session) {
        is AuthState.Active -> Routes.ENROLL
        else -> Routes.LOGIN
    }

    NavHost(navController = navController, startDestination = start) {

        composable(Routes.LOGIN) {
            LoginScreen(
                onSignedIn = {
                    navController.navigate(Routes.ENROLL) {
                        popUpTo(Routes.LOGIN) { inclusive = true }
                    }
                }
            )
        }

        composable(Routes.ENROLL) {
            EnrollScreen(
                onContinue = {
                    navController.navigate(Routes.DASHBOARD) {
                        popUpTo(Routes.ENROLL) { inclusive = true }
                    }
                },
                onBack = { navController.popBackStack() }
            )
        }

        composable(Routes.DASHBOARD) {
            DashboardScreen(
                onOpenCase = { c ->
                    navController.navigate(Routes.case(c.id))
                },
                onProfile = { navController.navigate(Routes.PROFILE) }
            )
        }

        composable(
            route = Routes.CASE,
            arguments = listOf(navArgument(Routes.ARG_CASE_ID) { type = NavType.StringType })
        ) { backStackEntry ->
            val caseId = backStackEntry.arguments?.getString(Routes.ARG_CASE_ID).orEmpty()
            CaseDetailScreen(
                caseId = caseId,
                onBack = { navController.popBackStack() },
                onOpenCollection = { remote ->
                    navController.navigate(Routes.collection(caseId, remote.id))
                }
            )
        }

        composable(
            route = Routes.COLLECTION,
            arguments = listOf(
                navArgument(Routes.ARG_CASE_ID) { type = NavType.StringType },
                navArgument(Routes.ARG_COLLECTION_ID) { type = NavType.StringType }
            )
        ) { backStackEntry ->
            val caseId = backStackEntry.arguments?.getString(Routes.ARG_CASE_ID).orEmpty()
            val collectionId = backStackEntry.arguments?.getString(Routes.ARG_COLLECTION_ID).orEmpty()
            val name = container.store.collection(caseId, collectionId)?.name ?: ""
            CollectionScreen(
                caseId = caseId,
                collectionId = collectionId,
                collectionName = name,
                onBack = { navController.popBackStack() },
                onPhoto = { navController.navigate(Routes.photo(caseId, collectionId)) },
                onVideo = { navController.navigate(Routes.video(caseId, collectionId)) }
            )
        }

        composable(
            route = Routes.PHOTO,
            arguments = listOf(
                navArgument(Routes.ARG_CASE_ID) { type = NavType.StringType },
                navArgument(Routes.ARG_COLLECTION_ID) { type = NavType.StringType }
            )
        ) { backStackEntry ->
            CameraCaptureScreen(
                mode = CameraMode.PHOTO,
                caseId = backStackEntry.arguments?.getString(Routes.ARG_CASE_ID).orEmpty(),
                collectionId = backStackEntry.arguments?.getString(Routes.ARG_COLLECTION_ID).orEmpty(),
                onBack = { navController.popBackStack() },
                onCaptured = { navController.popBackStack() }
            )
        }

        composable(
            route = Routes.VIDEO,
            arguments = listOf(
                navArgument(Routes.ARG_CASE_ID) { type = NavType.StringType },
                navArgument(Routes.ARG_COLLECTION_ID) { type = NavType.StringType }
            )
        ) { backStackEntry ->
            CameraCaptureScreen(
                mode = CameraMode.VIDEO,
                caseId = backStackEntry.arguments?.getString(Routes.ARG_CASE_ID).orEmpty(),
                collectionId = backStackEntry.arguments?.getString(Routes.ARG_COLLECTION_ID).orEmpty(),
                onBack = { navController.popBackStack() },
                onCaptured = { navController.popBackStack() }
            )
        }

        composable(Routes.PROFILE) {
            ProfileScreen(
                onBack = { navController.popBackStack() },
                onSignedOut = {
                    navController.navigate(Routes.LOGIN) {
                        popUpTo(navController.graph.findStartDestination().id) { inclusive = true }
                    }
                }
            )
        }
    }
}