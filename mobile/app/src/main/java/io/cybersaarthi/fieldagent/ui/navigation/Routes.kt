package io.cybersaarthi.fieldagent.ui.navigation

object Routes {
    const val ONBOARDING = "onboarding"
    const val CONNECT = "connect"
    const val QR = "connect/qr"
    const val LAN = "connect/lan"
    const val MANUAL = "connect/manual"
    const val LOGIN = "login"
    const val ENROLL = "enroll"
    const val DASHBOARD = "dashboard"
    const val FIELD = "field"
    const val PROFILE = "profile"
    const val CASE = "case/{caseId}"
    const val COLLECTION = "collection/{caseId}/{collectionId}"
    const val TRANSFER = "transfer/{caseId}/{collectionId}"
    const val PHOTO = "photo/{caseId}/{collectionId}"
    const val VIDEO = "video/{caseId}/{collectionId}"

    fun case(caseId: String) = "case/$caseId"
    fun collection(caseId: String, collectionId: String) = "collection/$caseId/$collectionId"
    fun transfer(caseId: String, collectionId: String) = "transfer/$caseId/$collectionId"
    fun photo(caseId: String, collectionId: String) = "photo/$caseId/$collectionId"
    fun video(caseId: String, collectionId: String) = "video/$caseId/$collectionId"

    const val ARG_CASE_ID = "caseId"
    const val ARG_COLLECTION_ID = "collectionId"
}
