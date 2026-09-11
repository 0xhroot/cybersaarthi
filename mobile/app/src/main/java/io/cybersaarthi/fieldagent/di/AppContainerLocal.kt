package io.cybersaarthi.fieldagent.di

import androidx.compose.runtime.compositionLocalOf
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.compose.runtime.Composable
import io.cybersaarthi.fieldagent.AppContainer

val LocalAppContainer = compositionLocalOf<AppContainer> { error("AppContainer not provided") }

/** Retains a ViewModel across configuration changes using the app container. */
@Composable
inline fun <reified VM : ViewModel> containerViewModel(
    crossinline create: (AppContainer) -> VM
): VM {
    val container = LocalAppContainer.current
    return viewModel(
        key = VM::class.java.name,
        factory = viewModelFactory { initializer { create(container) } }
    )
}